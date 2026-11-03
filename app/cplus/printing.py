"""Compact business print view over an already-authorized immutable projection."""
from html import escape
from urllib.parse import quote

LABELS={'revenue':'营业收入','net_profit_parent':'归母净利润','operating_cash_flow':'经营现金流',
        'total_assets':'总资产','total_liabilities':'总负债'}


def render_projection(ref,resolved,projection,company_name):
    def text(value):
        return escape(str(value))
    def period(value):
        value=value or {}
        return value.get('as_of_date') or ' 至 '.join(x for x in [value.get('period_start'),value.get('period_end')] if x) or '期间未提供'
    def source_link(value):
        source=value.get('source_ref') or value
        identifier=source.get('document_id')
        revision=source.get('source_revision')
        page=value.get('physical_page')
        if not(identifier and revision and isinstance(page,int) and page>0):
            return '见完整来源记录'
        if source.get('kind')=='ocr' and source.get('artifact_id'):
            href=f"/api/documents/{quote(identifier,safe='')}/parse-artifacts/{quote(source['artifact_id'],safe='')}/file#page={page}"
        else:
            href=f"/api/documents/{quote(identifier,safe='')}/file?source_revision={quote(revision,safe='')}#page={page}"
        return f'<a href="{escape(href,quote=True)}">原 PDF 第 {page} 页</a>'
    financial=[]
    for row in projection['financial']:
        name=row.get('company_name') or company_name(row.get('company_id'))
        if row.get('normalized_decimal') is not None and row.get('normalized_unit'):
            amount=str(row['normalized_decimal'])+' '+{'CNY_YUAN':'元（人民币）'}.get(row['normalized_unit'],row['normalized_unit'])
        else:
            amount=str(row.get('raw_decimal') or row.get('value_decimal') or '缺失')+' '+str(row.get('raw_unit') or row.get('unit') or '单位未提供')
        state='保存时已确认' if row.get('financial_review')=='local_operator_confirmed' and row.get('receipt_ref') else '候选 · 未核准'
        refs=row.get('evidence_refs') or []
        financial.append('<tr>'+''.join(f'<td>{text(x)}</td>' for x in [name,LABELS.get(row.get('metric_key'),row.get('metric_key') or '指标'),period(row.get('time')),amount,state])+f"<td>{'<br>'.join(source_link(r) for r in refs[:2]) or source_link(row)}</td></tr>")
    evidence=[]
    for item in projection['evidence'][:30]:
        value=str(item.get('text') or '')
        excerpt=value[:600]+('［节选，全文见CSV/XLSX］' if len(value)>600 else '')
        evidence.append(f"<article class=excerpt><small>{source_link(item)} · 来源转录/解释状态以原保存记录为准</small><p>{text(excerpt)}</p></article>")
    snapshot=resolved['snapshot']
    title=snapshot.get('title') or snapshot.get('question') or {'peer_comparison_v1':'同行财务候选对照','annual_diff_v1':'双年经营原文对照','checkup_v1':'财报体检观察'}.get(ref['domain'],'研究结果')
    state='保存版本来源当前可复验' if resolved['display_status']=='current' else '历史快照 · 当前来源已变化或不可复验'
    finance_html=('<table><thead><tr>'+''.join(f'<th>{x}</th>'for x in ['企业','指标','实际期间','金额与单位','审核状态','出处'])+'</tr></thead><tbody>'+''.join(financial)+'</tbody></table>') if financial else '<p>本快照没有可导出的结构化财务数值；缺失不补零。</p>'
    interpretation=next((row['value'] for row in projection['overview'] if row['field']=='interpretation'),None) or '此版本未生成额外 AI 解释。'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>FinDoc研究快照</title><style>body{{font:13px system-ui,sans-serif;color:#17324a;margin:36px;line-height:1.7}}h1{{font-size:27px;margin:8px 0}}h2{{font-size:19px;margin-top:28px}}table{{border-collapse:collapse;width:100%;font-size:11px}}td,th{{border-bottom:1px solid #dbe3ea;padding:8px;text-align:left;overflow-wrap:anywhere}}th{{background:#edf4f7}}small,.meta{{color:#627487}}.excerpt{{border-left:3px solid #69a3b0;padding-left:14px;margin:16px 0;break-inside:avoid}}a{{color:#176e86}}@media print{{body{{margin:14mm}}tr{{break-inside:avoid}}h2{{break-after:avoid}}}}</style><h1>FinDoc 研究快照</h1><h2>{text(title)}</h2><p class=meta>{text(state)} · 固定版本 {ref['revision']}</p><p>原文、候选与 AI 待审结果分别保留；导出不构成人工财务核准。</p><h2>财务数据与实际期间</h2>{finance_html}<h2>解读与核查</h2><p>{text(interpretation)}</p><h2>来源与原文节选</h2>{''.join(evidence) or '<p>此快照未保存原文摘录；请核查原始来源。</p>'}<p class=meta>业务摘要仅作阅读展示。完整原始金额、期间、来源与标识见 CSV/XLSX。<br>快照域：{text(ref['domain'])}<br>快照 SHA：{text(ref['payload_sha256'])}</p></html>'''
