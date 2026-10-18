from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agent.financial_facts import FinancialFactKey, FinancialFactRepository
from app.agent.tool_loop import ToolExecutionContext, ToolSpec
from app.rag.retriever import Retriever, SearchHit


def revenue_growth_rate_v1(current: Decimal, previous: Decimal) -> Decimal:
    """Frozen legacy formula: preserve ambient Decimal context and signed denominator."""
    return ((current - previous) / previous * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def financial_period_change_v1(current: Decimal, previous: Decimal) -> dict[str, object]:
    """D11 deterministic arithmetic; callers must admit persisted facts first.

    Exact subtraction before rounding; cents and percentage points use HALF_UP.
    A local, operand-sized context makes the new version independent of ambient
    precision. The signed denominator is deliberately compatible with legacy v1.
    """
    if not all(isinstance(v, Decimal) and v.is_finite() for v in (current, previous)):
        raise ValueError("finite Decimal amounts required")
    precision = max(
        50,
        max(v.adjusted() for v in (current, previous))
        - min(int(v.as_tuple().exponent) for v in (current, previous))
        + 32,
        abs(current.adjusted() - previous.adjusted()) + 32,
    )
    with localcontext(Context(prec=precision, rounding=ROUND_HALF_UP)):
        delta = (current - previous).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        percentage = None if previous == 0 else revenue_growth_rate_v1(current, previous)
    transition = (
        "negative_to_positive"
        if previous < 0 < current
        else "positive_to_negative"
        if current < 0 < previous
        else "both_negative"
        if current < 0 and previous < 0
        else "ordinary"
    )
    return {
        "absolute_change": format(delta, "f"),
        "percentage_change": format(percentage, "f") if percentage is not None else None,
        "percentage_reason": "zero_base" if previous == 0 else None,
        "sign_transition": transition,
        "limitations": [
            {
                "code": "negative_base",
                "message": "上期为负数，按带符号分母计算；百分比的数学符号不能直接表示经营改善或恶化。",
            }
        ]
        if previous < 0
        else [],
    }


class FinancialMetricErrorCode(StrEnum):
    """财务指标计算错误码枚举。"""

    UNSUPPORTED_METRIC = "unsupported_metric"
    """不支持的指标。"""
    SOURCE_NOT_AVAILABLE = "source_not_available"
    """财务数值来源不可用。"""
    INVALID_PERIOD_ORDER = "invalid_period_order"
    """期间顺序不合法。"""
    UNIT_CONFLICT = "unit_conflict"
    """单位不一致。"""
    DIVISION_BY_ZERO = "division_by_zero"
    """除零错误。"""


class FinancialMetricError(RuntimeError):
    """财务指标计算因安全业务规则无法继续时抛出的稳定异常。

    输入：
        稳定错误码和不包含内部数据的安全消息。
    输出：
        保存可供业务测试和协议适配器识别的错误信息。
    失败：
        由调用方在可信来源、期间、单位或除零校验失败时抛出。
    责任边界：
        不保存原始异常、来源归属详情、数值或存储信息，
        也不决定loop如何向模型回填错误。
    """

    def __init__(self, code: FinancialMetricErrorCode, message: str) -> None:
        """保存稳定错误码和安全消息。"""
        super().__init__(message)
        self.code = code
        self.message = message


class SearchFinanceDocsArguments(BaseModel):
    """模型申请财报检索时允许提交的严格业务参数。

    输入：
        模型提交的 query 和可选 top_k
    输出：
        规范化后的严格搜索参数
    失败：
        类型，范围或额外字段不合法时抛出 ValidationError
    边界：
        不包含 workspace document 或任意服务端可信字段
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
        ),
    ] = Field(
        description="需要在当前可信文档范围内检索的问题或关键词",
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=5,
        description="最多返回的检索结果数量",
    )


def _search_hit_to_output(hit: SearchHit) -> dict[str, object]:
    """把单个稳定SearchHit显式转换成工具公开输出字段。

    输入：
        Retriever返回的SearchHit。
    输出：
        只包含冻结公开字段的可JSON序列化字典。
    失败：
        非SearchHit输入由调用方合同排除，本函数不吞掉属性或序列化错误。
    责任边界：
        不使用asdict自动扩大公开合同，不修改命中内容，也不生成引用真值。
    """
    output: dict[str, object] = {
        "score": hit.score,
        "chunk_id": hit.chunk_id,
        "text": hit.text,
        "page": hit.page,
        "source_file": hit.source_file,
        "type": hit.type,
        "section": hit.section,
        "table_md": hit.table_md,
    }
    # 只保留 Retriever 实际返回的身份；旧离线路径缺省时不得从上下文补造。
    if hit.workspace_id is not None:
        output["workspace_id"] = hit.workspace_id
    if hit.document_id is not None:
        output["document_id"] = hit.document_id
    return output


class SearchFinanceDocsTool:
    """把现有Retriever包装成受可信文档范围约束的财报搜索工具。

    输入：
        构造时注入可复用的Retriever；
        调用时接收服务端ToolExecutionContext和已通过schema校验的query、top_k。
    输出：
        返回包含查询、请求数量、命中数量、空结果标志和结构化hits的可序列化字典。
    正常路径：
        使用服务端workspace和document过滤调用Retriever一次，并显式序列化SearchHit。
    失败：
        Retriever、embedder或store异常继续向协议层传播，由loop映射为安全ToolError。
    责任边界：
        不从模型参数构造可信上下文，不执行认证或授权，
        不复制检索实现，不调用RAG LLM，也不生成最终回答。
    """

    def __init__(self, retriever: Retriever) -> None:
        """保存应用启动时注入的Retriever。

        输入：
            retriever是项目现有的财报检索器。
        输出：
            构造可复用的搜索工具对象。
        正常路径：
            保存依赖，不执行embedding或store查询。
        失败：
            Retriever构造或运行异常不在本方法中处理。
        责任边界：
            只绑定稳定基础设施依赖，不保存任何模型参数或单次请求的可信上下文。
        """
        self._retriever = retriever

    def __call__(
        self,
        execution_context: ToolExecutionContext,
        query: str,
        top_k: int = 5,
    ) -> dict[str, object]:
        """在服务端可信范围内执行一次财报检索。

        输入：
            execution_context包含服务端workspace和document过滤；
            query和top_k是已通过严格schema校验的模型业务参数。
        输出：
            返回稳定、可JSON序列化的搜索结果；空检索返回empty为True和空hits。
        正常路径：
            把可信上下文、过滤条件、query和top_k传给现有Retriever一次。
        失败：
            Retriever及其底层依赖异常向外传播，等待协议层统一安全映射。
        责任边界：
            不允许模型覆盖workspace/document，不调用LLM，
            不生成答案，也不执行财务计算。
        """
        hits = self._retriever.retrieve(
            query,
            context=execution_context.trusted_context,
            top_k=top_k,
            filters=execution_context.filters,
        )
        hits_summary = [_search_hit_to_output(hit) for hit in hits]
        return {
            "query": query,
            "requested_top_k": top_k,
            "result_count": len(hits),
            "empty": len(hits) == 0,
            "hits": hits_summary,
        }


class CalculateFinancialMetricArguments(BaseModel):
    """模型申请确定性财务指标计算时允许提交的严格参数。

    输入：
        白名单metric_id和两条待验证的来源引用。
    输出：
        规范化后的指标选择与本期、上期来源键。
    失败：
        指标不在白名单、来源为空、类型错误或出现额外字段时抛出ValidationError。
    责任边界：
        不接受workspace、document、数值、单位、期间、公式或最终结果。
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    metric_id: Literal["revenue_growth_rate"] = Field(
        description="今天唯一支持的营业收入增长率指标",
    )

    current_period_source_ref: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
        ),
    ] = Field(
        description="本期营业收入事实的待验证来源引用",
    )

    previous_period_source_ref: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
        ),
    ] = Field(
        description="上期营业收入事实的待验证来源引用",
    )


class CalculateFinancialMetricTool:
    """保存服务端注入的可信财务事实repository。

    输入：
        repository提供受可信执行上下文约束的财务事实查询。
    输出：
        构造可复用的确定性计算工具。
    失败：
        repository自身的构造错误不在此处理。
    责任边界：
        只保存依赖，不读取事实、不执行公式。
    """

    def __init__(self, repository: FinancialFactRepository) -> None:
        """保存服务端注入的可信财务事实repository。

        输入：
            repository提供受可信执行上下文约束的财务事实查询。
        输出：
            构造可复用的确定性计算工具。
        失败：
            repository自身的构造错误不在此处理。
        责任边界：
            只保存依赖，不读取事实、不执行公式。
        """
        self._repository = repository

    def __call__(
        self,
        execution_context: ToolExecutionContext,
        metric_id: Literal["revenue_growth_rate"],
        current_period_source_ref: str,
        previous_period_source_ref: str,
    ) -> dict[str, object]:
        """使用两条可信营业收入事实计算固定增长率。

        输入：
            execution_context提供服务端可信范围；
            其余参数是经过严格schema校验的指标和待验证来源键。
        输出：
            返回可JSON序列化的计算值、单位、公式标识和来源追踪。
        失败：
            来源、期间、单位或除零规则不满足时抛出FinancialMetricError；
            repository内部异常向协议层传播。
        责任边界：
            来源键只用于repository查询，数值、单位、期间和结果均不能由模型决定。
        """
        # 确认metric_id是唯一白名单指标
        if metric_id != "revenue_growth_rate":
            raise FinancialMetricError(
                FinancialMetricErrorCode.UNSUPPORTED_METRIC,
                "不支持的财务指标",
            )
        # repository查询本期revenue事实
        current = self._repository.find_fact(
            execution_context=execution_context,
            source_ref=current_period_source_ref,
            fact_key=FinancialFactKey.REVENUE,
        )
        if current is None:
            raise FinancialMetricError(
                FinancialMetricErrorCode.SOURCE_NOT_AVAILABLE,
                "财务数值来源不可用",
            )
        # repository查询上期revenue事实
        previous = self._repository.find_fact(
            execution_context=execution_context,
            source_ref=previous_period_source_ref,
            fact_key=FinancialFactKey.REVENUE,
        )
        if previous is None:
            raise FinancialMetricError(
                FinancialMetricErrorCode.SOURCE_NOT_AVAILABLE,
                "财务数值来源不可用",
            )
        # 验证本期和上期fact的期间顺序
        if current.period <= previous.period:
            raise FinancialMetricError(
                FinancialMetricErrorCode.INVALID_PERIOD_ORDER,
                "财务事实期间顺序无效",
            )
        # 两期unit不同 → unit_conflict
        if current.unit != previous.unit:
            raise FinancialMetricError(
                FinancialMetricErrorCode.UNIT_CONFLICT,
                "财务事实单位不兼容",
            )
        if previous.value == 0:
            raise FinancialMetricError(
                FinancialMetricErrorCode.DIVISION_BY_ZERO,
                "财务指标分母不能为零",
            )
        # Decimal固定公式计算 ROUND_HALF_UP保留两位小数
        growth_rate = revenue_growth_rate_v1(current.value, previous.value)
        sources = [
            {
                "role": "current_period",
                "source_ref": current.source_ref,
                "fact_key": current.fact_key.value,
                "period": current.period,
                "value": format(current.value, "f"),
                "unit": current.unit.value,
            },
            {
                "role": "previous_period",
                "source_ref": previous.source_ref,
                "fact_key": previous.fact_key.value,
                "period": previous.period,
                "value": format(previous.value, "f"),
                "unit": previous.unit.value,
            },
        ]

        return {
            "metric_id": metric_id,
            "value": format(growth_rate, "f"),
            "unit": "PERCENT",
            "formula_id": "revenue_growth_rate_v1",
            "sources": sources,
        }


def build_search_finance_tool_registry(*, retriever: Retriever) -> dict[str, ToolSpec]:
    """用传入的检索器构造独立的单工具注册表，供真实 runtime 使用。

    输入：应用已创建的 Retriever，不在此初始化模型、向量库或事实库。
    输出：只有 search_finance_docs 的新字典，复用既有 schema 和 handler。
    失败：ToolSpec 构造错误向装配入口传播；构造不执行检索。
    边界：不注册计算工具，不读取评测样例或单次请求的授权范围。
    """
    return {
        "search_finance_docs": ToolSpec(
            arguments_schema=SearchFinanceDocsArguments,
            handler=SearchFinanceDocsTool(retriever),
            description="在当前服务端可信财报范围内检索与问题相关的文档片段。",
        ),
    }


def build_finance_tool_registry(
    *,
    retriever: Retriever,
    financial_fact_repository: FinancialFactRepository,
) -> dict[str, ToolSpec]:
    """使用服务端可信依赖构造财报业务工具allowlist。

    输入：
        项目现有Retriever和服务端可信FinancialFactRepository。
    输出：
        返回同时注册搜索与确定性计算工具的ToolSpec字典。
    正常路径：
        两个工具分别绑定严格参数schema和已注入基础设施依赖的handler。
    失败：
        ToolSpec或具体工具构造失败时向应用启动层传播。
    责任边界：
        只负责依赖装配和工具注册，不读取模型消息、
        不创建单次请求的可信上下文，也不执行搜索或计算。
    """
    registry = build_search_finance_tool_registry(retriever=retriever)
    registry["calculate_financial_metric"] = ToolSpec(
        arguments_schema=CalculateFinancialMetricArguments,
        handler=CalculateFinancialMetricTool(financial_fact_repository),
        description="根据两条待验证的营业收入来源引用计算固定营业收入增长率。",
    )
    return registry
