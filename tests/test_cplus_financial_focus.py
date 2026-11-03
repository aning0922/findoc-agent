"""A report's comparative financial period must survive chart→context, no human grants."""
import asyncio
from copy import deepcopy
from uuid import uuid4
import pytest
from app.cplus.focus import FinancialFocusService
from app.documents.preparation import DocumentTaskPreparer
from app.financial_statements_v3 import StatementService
from app.retrieval_v2.models import RetrievalError
from tests.test_finance_v2 import assembled,synthetic_pdf


def test_focus_resolves_actual_comparative_period_and_rejects_browser_changes(tmp_path):
    h,company,doc,source=assembled(tmp_path,synthetic_pdf())
    statements=StatementService(tmp_path,h.service)
    preparer=DocumentTaskPreparer(document_service=h.service.documents,sources=h.service,workspace_id='demo')
    service=FinancialFocusService(statements,preparer)
    async def run():
        collection=await statements.collect(str(uuid4()),doc,source['source_revision'])
        cell=next(c for c in collection['cells'] if c['time']['kind']=='instant' and c['time']['as_of_date'].startswith('2030'))
        focus=await service.resolve(cell['cell_id'],cell['cell_revision'],cell['payload_sha256'])
        assert focus['source_ref']['report_year']==2031
        assert focus['time']['as_of_date']=='2030-12-31' and focus['financial_authority'] is False
        from app.retrieval_v2 import SourceRef
        refs=[SourceRef.model_validate(focus['source_ref'])]
        assert service.verify(focus,refs).time==cell['time']
        changed=deepcopy(focus)
        changed['time']['as_of_date']='2031-12-31'
        with pytest.raises(RetrievalError,match='focus_cell_changed'):
            service.verify(changed,refs)
        changed=deepcopy(focus)
        changed['normalized_decimal']='9999999'
        with pytest.raises(RetrievalError,match='focus_cell_changed'):
            service.verify(changed,refs)
        with pytest.raises(RetrievalError,match='focus_source_changed'):
            service.verify(focus,[])
    asyncio.run(run())
