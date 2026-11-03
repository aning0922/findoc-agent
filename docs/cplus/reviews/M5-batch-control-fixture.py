import asyncio,time
from uuid import uuid4
from tests.test_cplus_batch_research import setup,approved
from app.retrieval_v2.models import RetrievalError
from contextlib import contextmanager
import pytest


def test_stale_revision_source_independent_cancel_owner_expiry(tmp_path):
 async def run():
  entered,release=asyncio.Event(),asyncio.Event();calls=[];broken=[False]
  async def execute(c,op,i):calls.append(op);entered.set();await release.wait();return dict(domain='retrieval_v2',state='completed',payload={})
  s,i,body=setup(tmp_path,execute)
  @contextmanager
  def guard(identity,fence):
   if broken[0] and fence.get('selected_sources'):raise RetrievalError('source_changed')
   yield
  s.guard=guard
  plan=(await s.plan(body,i))['result'];request=approved(plan)
  ack=await asyncio.wait_for(s.start(request,i,background=True),.5);await entered.wait();batch=ack['result']['batch_id']
  assert ack['state']=='completed' and ack['result']['completion_via_get']
  assert (await s.read(batch,i))['revision']>ack['result']['revision']
  for other in (i.model_copy(update={'principal_id':'other'}),i.model_copy(update={'expires_at':time.time()-1})):
   with pytest.raises(RetrievalError):await s.cancel(batch,dict(operation_id=str(uuid4()),expected_revision=1),other)
  assert [c['state'] for c in (await s.read(batch,i))['cells']]==['dispatching','queued','queued','queued']
  with pytest.raises(RetrievalError,match='revision_conflict'):await s.cancel(batch,dict(operation_id=str(uuid4()),expected_revision=999),i)
  broken[0]=True
  cancel=dict(operation_id=str(uuid4()),expected_revision=1)
  receipt=await s.cancel(batch,cancel,i)
  assert receipt['result']['cancelled_queued']==3
  assert [c['state'] for c in (await s.read(batch,i))['cells']]==['dispatching','cancelled','cancelled','cancelled']
  assert await s.cancel(batch,cancel,i)==receipt
  broken[0]=False;release.set();await asyncio.gather(*s._tasks)
  assert [c['state'] for c in (await s.read(batch,i))['cells']]==['completed','cancelled','cancelled','cancelled']
  assert len(calls)==1 and await s.start(request,i,background=True)==ack
 asyncio.run(run())


def test_cancel_precommit_expiry_rolls_back(tmp_path):
 async def run():
  entered=asyncio.Event();never=asyncio.Event()
  async def execute(*args):entered.set();await never.wait()
  s,i,body=setup(tmp_path,execute);plan=(await s.plan(body,i))['result'];ack=await s.start(approved(plan),i,background=True);await entered.wait()
  def expire(identity,fence):
   if fence.get('cancellation_of'):object.__setattr__(identity,'expires_at',time.time()-1)
  s.commit_check=expire;op=str(uuid4())
  with pytest.raises(RetrievalError,match='before_commit'):await s.cancel(ack['result']['batch_id'],dict(operation_id=op,expected_revision=1),i)
  with s.store.tx() as db:
   assert [r[0] for r in db.execute('SELECT state FROM cells ORDER BY rowid')]==['dispatching','queued','queued','queued']
   assert db.execute('SELECT state FROM operations WHERE id=?',(op,)).fetchone()[0]=='unknown'
  tasks=list(s._tasks)
  for task in tasks:task.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
 asyncio.run(run())


def test_interruption_restart_reads_and_false_default_never_dispatch(tmp_path):
 async def run():
  entered,never=asyncio.Event(),asyncio.Event();calls=[]
  async def execute(c,op,i):calls.append(op);entered.set();await never.wait()
  s,i,body=setup(tmp_path,execute);receipt=await s.plan(body,i)
  assert await s.plan({**body,'generate_explanations':False},i)==receipt
  with pytest.raises(RetrievalError,match='operation_conflict'):await s.plan({**body,'generate_explanations':True},i)
  request=approved(receipt['result']);ack=await s.start(request,i,background=True);await entered.wait();tasks=list(s._tasks)
  for task in tasks:task.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
  restarted,_,_=setup(tmp_path,execute)
  assert all(c['state']=='unknown' for c in (await restarted.read(ack['result']['batch_id'],i))['cells'])
  assert await restarted.start(request,i,background=True)==ack
  await restarted.list(i);await restarted.read(ack['result']['batch_id'],i)
  assert not restarted._tasks and len(calls)==1
 asyncio.run(run())
