from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from app.agent.tool_loop import ToolExecutionContext


class FinancialFactKey(StrEnum):
    """财务指标键值"""

    NET_PROFIT_PARENT = "net_profit_parent"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    REVENUE = "revenue"
    """营业收入"""


class FinancialUnit(StrEnum):
    """财务指标单位"""

    CNY_100_MILLION = "CNY_100_MILLION"
    """人民币亿元"""
    CNY_YUAN = "CNY_YUAN"
    """人民币元"""


@dataclass(frozen=True)
class FinancialFact:
    """服务端可信数值来源中的一条不可变财务事实。

    输入：
        workspace_id、document_id和source_ref标识事实的可信来源范围；
        fact_key、period、Decimal类型value和unit描述事实内容。
    输出：
        保存来源、期间、数值和单位的可追溯结构化财务事实。
    正常路径：
        三个标识符非空，事实类型和单位属于白名单，
        period为正整数，value为有限Decimal。
    失败：
        字段类型错误时抛出TypeError；字符串为空、期间非正数
        或Decimal不是有限值时抛出ValueError。
    责任边界：
        只校验单条事实的结构和基本值域；
        不查询repository，不验证其是否属于当前执行上下文，
        不执行单位换算或财务指标计算。
    """

    workspace_id: str
    """工作区ID"""

    document_id: str
    """文档ID"""

    source_ref: str
    """来源引用"""

    fact_key: FinancialFactKey
    """财务指标键值"""

    period: int
    """时期"""

    value: Decimal
    """数值"""

    unit: FinancialUnit
    """单位"""

    def __post_init__(self) -> None:
        """校验财务事实的来源标识、枚举、期间、数值和单位。

        输入：
            当前FinancialFact实例的全部七个字段。
        输出：
            校验成功时不返回值，允许不可变事实完成构造。
        正常路径：
            来源标识为非空字符串，fact_key和unit属于白名单，
            period为非bool正整数，value为非bool有限Decimal。
        失败：
            Python类型不符合合同时抛出TypeError；
            字符串为空、period非正数或value非有限值时抛出ValueError。
        责任边界：
            只校验当前记录本身，不访问可信repository，
            不判断workspace/document授权，也不计算增长率。
        """
        if not isinstance(self.workspace_id, str):
            raise TypeError(f"无效的工作区ID: {self.workspace_id}")
        if not self.workspace_id.strip():
            raise ValueError(f"无效的工作区ID: {self.workspace_id}")
        if not isinstance(self.document_id, str):
            raise TypeError(f"无效的文档ID: {self.document_id}")
        if not self.document_id.strip():
            raise ValueError(f"无效的文档ID: {self.document_id}")
        if not isinstance(self.source_ref, str):
            raise TypeError(f"无效的来源引用: {self.source_ref}")
        if not self.source_ref.strip():
            raise ValueError(f"无效的来源引用: {self.source_ref}")
        # fact_key 必须是白名单枚举。
        if not isinstance(self.fact_key, FinancialFactKey):
            raise TypeError(f"无效的财务指标键值: {self.fact_key}")
        # period 必须是真正的正整数，显式拒绝 bool
        if isinstance(self.period, bool) or not isinstance(self.period, int):
            raise TypeError(f"无效的时期: {self.period}")
        if self.period <= 0:
            raise ValueError(f"无效的时期: {self.period}")
        # value 必须是真正的 Decimal，显式拒绝 bool
        if isinstance(self.value, bool) or not isinstance(self.value, Decimal):
            raise TypeError(f"无效的数值: {self.value}")
        # value 必须是有限值，拒绝 NaN 和正负无穷
        if not self.value.is_finite():
            raise ValueError(f"无效的数值: {self.value}")
        # unit 必须是白名单枚举。
        if not isinstance(self.unit, FinancialUnit):
            raise TypeError(f"无效的单位: {self.unit}")


class FinancialFactRepository(Protocol):
    """定义按服务端可信范围查询结构化财务事实的最小端口。

    输入：
        当前工具执行上下文、待验证来源引用和白名单事实类型。
    输出：
        返回当前workspace/document中的匹配事实；不可见或不存在时返回None。
    正常路径：
        实现使用服务端上下文限制查询范围，不进行全局source_ref信任。
    失败：
        具体存储实现异常可以向业务层传播，等待协议层安全映射。
    责任边界：
        只定义可信事实查询合同，不抽取文本数值，
        不执行单位换算、财务公式或模型调用。
    """

    def find_fact(
        self,
        *,
        execution_context: ToolExecutionContext,
        source_ref: str,
        fact_key: FinancialFactKey,
    ) -> FinancialFact | None:
        """在服务端可信workspace/document范围内查找一条财务事实。

        输入：
            execution_context提供可信workspace和document；
            source_ref是待验证来源键，fact_key是应用白名单事实类型。
        输出：
            匹配时返回FinancialFact；来源不存在、不属于当前范围
            或当前上下文没有document_id时返回None。
        正常路径：
            查询范围同时包含workspace、document、source_ref和fact_key。
        失败：
            具体repository实现的内部异常向调用方传播。
        责任边界：
            不信任模型提供的来源归属，不向调用方披露跨范围记录，
            不判断期间顺序，也不执行财务计算。
        """
        ...


class InMemoryFinancialFactRepository(FinancialFactRepository):
    """使用服务端提供的有限内存fixture实现可信财务事实查询。

    输入：
        构造时接收已验证的FinancialFact列表。
    输出：
        提供受ToolExecutionContext约束的进程内事实查找。
    正常路径：
        保存输入列表的tuple副本，并按复合范围返回唯一可见事实。
    失败：
        本实现不吞掉FinancialFact构造或运行期程序错误。
    责任边界：
        仅用于当前有限、非持久的可信数值fixture；
        不代表真实财报结构化抽取、OCR、财务数据库或数据平台。
    """

    def __init__(self, facts: list[FinancialFact]) -> None:
        """复制并保存服务端准备的有限可信事实集合。

        输入：
            facts是已经构造完成的FinancialFact列表。
        输出：
            建立不受调用方后续列表修改影响的tuple快照。
        正常路径：
            只保存事实，不执行查询或计算。
        失败：
            单条事实的结构错误应在FinancialFact构造阶段被拒绝。
        责任边界：
            不接收模型生成的数值，不持久化数据，也不抽取财报文本。
        """
        self._facts: tuple[FinancialFact, ...] = tuple(facts)

    def find_fact(
        self,
        *,
        execution_context: ToolExecutionContext,
        source_ref: str,
        fact_key: FinancialFactKey,
    ) -> FinancialFact | None:
        """在当前可信workspace/document中遍历查找匹配事实。

        输入：
            execution_context提供服务端workspace和document；
            source_ref是待验证来源键，fact_key是白名单事实类型。
        输出：
            四字段范围匹配时返回FinancialFact，否则返回None。
        正常路径：
            从tuple快照中匹配workspace、document、source_ref和fact_key。
        失败：
            当前实现不吞掉上下文访问或程序错误。
        责任边界：
            没有document_id时拒绝扩大查询并返回None；
            不披露跨范围事实，不判断期间顺序，也不执行计算。
        """
        workspace_id = execution_context.trusted_context.workspace_id
        filters = execution_context.filters
        if filters is None or filters.document_id is None:
            return None
        document_id = filters.document_id

        for fact in self._facts:
            if (
                fact.workspace_id == workspace_id
                and fact.document_id == document_id
                and fact.source_ref == source_ref
                and fact.fact_key == fact_key
            ):
                return fact
        return None
