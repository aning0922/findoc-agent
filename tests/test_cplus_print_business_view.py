"""A printed business report must not leak internal rule JSON as original evidence."""
from app.cplus.printing import render_projection


def test_rules_are_readable_observations_and_technical_json_is_not_a_quote():
    raw='{"input_refs":["'+('unbroken-internal-reference-'*60)+'"]}'
    projection={'financial':[], 'evidence':[
        {'kind':'saved_checkup_rule','text':raw},
        {'kind':'structured_table','text':'['+raw+']'},
    ],'overview':[{'field':'interpretation','value':'核查口径与期间。<script>untrusted()</script>'}]}
    snapshot={'checkup_rules':[{'rule_id':'cash_profit_divergence','observation':'direction_diverges','input_refs':[]}]}
    html=render_projection({'domain':'template_run_v1','revision':1,'payload_sha256':'a'*64},
                           {'snapshot':snapshot,'display_status':'current'},projection,lambda _: '企业')
    assert '程序体检与核查' in html
    assert '现金流与利润方向对照' in html
    assert '所选两期方向不同' in html
    assert 'input_refs' not in html and 'unbroken-internal-reference' not in html
    assert '完整内容见CSV/XLSX' in html
    assert '<script>untrusted()' not in html
    assert '&lt;script&gt;' in html
