"""Confirmed household inventory. No inferred consumption or food-safety expiry."""
import os
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator


def name_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


class PantryItem(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str | None = Field(default=None, min_length=1, max_length=80)
    version: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal | None = Field(default=None, gt=0, le=100000, max_digits=10, decimal_places=2)
    unit: Literal['克', '毫升', '个', '份', '适量'] = '适量'
    amount_note: str = Field(default='', max_length=200)
    location: Literal['未说明', '冷藏', '冷冻', '常温'] = '未说明'
    kind: Literal['raw', 'cooked'] = 'raw'
    status: Literal['available', 'used_up'] = 'available'

    @model_validator(mode='after')
    def quantities(self):
        if (self.quantity is None) != (self.unit == '适量'):
            raise ValueError('Known quantities need a concrete unit')
        if (self.id is None) != (self.version == 0):
            raise ValueError('Existing items require their current version')
        if not name_key(self.name):
            raise ValueError('Empty normalized name')
        return self


class PantryUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    items: list[PantryItem] = Field(min_length=1, max_length=20)
    review_confirmed: bool = False

    @model_validator(mode='after')
    def unique_items(self):
        keys = [(name_key(i.name), i.location, i.kind) for i in self.items]
        ids = [i.id for i in self.items if i.id]
        if len(keys) != len(set(keys)) or len(ids) != len(set(ids)):
            raise ValueError('Duplicate inventory changes')
        return self


def revision(db, family_id):
    row = db.execute('SELECT version FROM pantry_revisions WHERE family_id=?', (family_id,)).fetchone()
    return row['version'] if row else 0


def reconfirm_days():
    try:
        return max(1, min(30, int(os.getenv('PANTRY_RECONFIRM_DAYS', '7'))))
    except ValueError:
        return 7


def item_dict(row, clock):
    value = dict(row)
    try:
        age = (clock.date() - datetime.fromisoformat(row['confirmed_at']).astimezone(clock.tzinfo).date()).days
        value['needs_reconfirmation'] = age < 0 or age >= reconfirm_days()
    except (ValueError, TypeError):
        value['needs_reconfirmation'] = True
    value.pop('name_key', None)
    return value


def snapshot(db, family_id, clock):
    return {'version': revision(db, family_id),
            'items': [item_dict(r, clock) for r in db.execute(
                'SELECT p.*,m.name AS member_name FROM pantry p JOIN members m ON m.id=p.updated_by WHERE p.family_id=? ORDER BY p.status,p.name_key,p.location,p.kind', (family_id,))],
            'reconfirm_days': reconfirm_days(),
            'note': '余量为家人确认的当前总量，不是本次购买量。更新时间仅用于核对记录，不代表食品保质期或安全保证。'}


def apply_update(db, m, data, s):
    if not db.execute('SELECT id FROM members WHERE id=? AND family_id=? AND active=1', (m['id'], m['family_id'])).fetchone():
        s.error(403, '成员访问已被撤销')
    if not data.review_confirmed:
        s.error(422, '请先核对实际食材和余量')
    if revision(db, m['family_id']) != data.version:
        s.error(409, '家里食材已被更新，请刷新后核对再保存')
    existing_count = db.execute('SELECT COUNT(*) FROM pantry WHERE family_id=?', (m['family_id'],)).fetchone()[0]
    if existing_count + sum(i.id is None for i in data.items) > 200:
        s.error(422, '食材记录已达当前版本上限，请更正或复用已有食材记录')
    saved = []
    # Caller owns the write transaction; a conflict rolls back every change.
    for item in data.items:
        old = None
        if item.id:
            old = db.execute('SELECT * FROM pantry WHERE id=? AND family_id=?', (item.id, m['family_id'])).fetchone()
            if not old:
                s.error(404, '食材记录不存在')
            if old['version'] != item.version:
                s.error(409, '这条食材已变化，请刷新后核对')
        duplicate = db.execute('SELECT id FROM pantry WHERE family_id=? AND name_key=? AND location=? AND kind=?',
                               (m['family_id'], name_key(item.name), item.location, item.kind)).fetchone()
        if duplicate and duplicate['id'] != item.id:
            s.error(409, '同位置已有这项食材，请更正原记录，填写当前总量')
        mid = item.id or s.uid()
        quantity = str(item.quantity) if item.quantity is not None else None
        # A used-up item never carries a positive available balance.
        if item.status == 'used_up':
            quantity, unit, amount_note = None, '适量', ''
        else:
            unit, amount_note = item.unit, item.amount_note
        values = (item.name, name_key(item.name), quantity, unit, amount_note, item.location,
                  item.kind, item.status, s.now(), m['id'])
        if old:
            db.execute('UPDATE pantry SET name=?,name_key=?,quantity=?,unit=?,amount_note=?,location=?,kind=?,status=?,confirmed_at=?,updated_by=?,version=version+1 WHERE id=?', (*values, mid))
        else:
            db.execute('INSERT INTO pantry (id,family_id,name,name_key,quantity,unit,amount_note,location,kind,status,confirmed_at,updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (mid, m['family_id'], *values))
        result = dict(db.execute('SELECT * FROM pantry WHERE id=?', (mid,)).fetchone())
        s.log_change(db, m, 'pantry', mid, 'update' if old else 'create', dict(old) if old else None, result)
        saved.append(mid)
    db.execute('INSERT INTO pantry_revisions VALUES (?,1) ON CONFLICT(family_id) DO UPDATE SET version=version+1', (m['family_id'],))
    return {'saved': True, 'kind': 'pantry', 'item_ids': saved, 'version': revision(db, m['family_id'])}


def register(app, s):
    @app.get('/api/pantry')
    def get_pantry(m=Depends(s.member)):
        with s.database() as db:
            db.execute('BEGIN')
            return snapshot(db, m['family_id'], datetime.now(s.TZ))

    @app.put('/api/pantry')
    def update_pantry(data: PantryUpdate, request: Request, m=Depends(s.member)):
        with s.database(True) as db:
            return s.idempotent(db, m, request.headers.get('Idempotency-Key'), 'pantry.update',
                                data.model_dump(mode='json'), lambda: apply_update(db, m, data, s))
