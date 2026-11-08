"""Bounded evidence for recommendations and deterministic shopping gaps."""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from .pantry import name_key, snapshot


def recommendation_context(db, m, s):
    clock = datetime.now(s.TZ)
    end, start = clock.date().isoformat(), (clock.date()-timedelta(days=6)).isoformat()
    stock = snapshot(db, m['family_id'], clock)
    total_actual = db.execute('SELECT COUNT(*) FROM records WHERE family_id=? AND day BETWEEN ? AND ? AND deleted=0', (m['family_id'], start, end)).fetchone()[0]
    actual = db.execute('SELECT day,meal,items,note FROM records WHERE family_id=? AND day BETWEEN ? AND ? AND deleted=0 ORDER BY day DESC,created_at DESC,id DESC LIMIT 14', (m['family_id'], start, end)).fetchall()
    menus = db.execute('SELECT day,meal,title,ingredients,method FROM menus WHERE family_id=? AND day BETWEEN ? AND ? ORDER BY day DESC,meal', (m['family_id'], start, end)).fetchall()
    usable = [i for i in stock['items'] if i['status']=='available' and i['kind']=='raw' and not i['needs_reconfirmation']]
    context = {'period': {'start': start, 'end': end}, 'inventory_revision': stock['version'],
               'records': [], 'history_menus': [], 'pantry': [],
               'coverage': {'total_records': total_actual, 'total_menus': len(menus), 'total_available_raw_items': len(usable),
                            'excluded_stock_items': len(stock['items'])-len(usable), 'details_truncated': False},
               'rules': '历史菜单是当前保存版本，不代表实际吃过。未记录不代表没吃；一次拒吃不永久排除。库存更新时间不是安全保证，熟食/已用完/待重确认食材不作为可用原料。临时补充不自动改变库存。'}
    for index, row in enumerate(actual[:14]):
        items = json.loads(row['items'])
        context['records'].append({'ref': f'R{index+1}', 'day': row['day'], 'meal': row['meal'], 'items': items[:10], 'note': row['note'][:200]})
        context['coverage']['details_truncated'] |= len(items)>10 or len(row['note'])>200
    for index, row in enumerate(menus[:15]):
        ingredients = json.loads(row['ingredients'])
        context['history_menus'].append({'ref': f'M{index+1}', 'day': row['day'], 'meal': row['meal'], 'title': row['title'], 'ingredients': ingredients[:10], 'method': row['method'][:200]})
        context['coverage']['details_truncated'] |= len(ingredients)>10 or len(row['method'])>200
    for index, item in enumerate(usable[:40]):
        context['pantry'].append({'ref': f'P{index+1}', **{k: item[k] for k in ('name', 'quantity', 'unit', 'amount_note', 'location', 'confirmed_at')}})
    # Avoid unbounded family-history payloads. Metadata always reports omissions.
    while len(s.encoded(context))>11000:
        largest = max(('records', 'history_menus', 'pantry'), key=lambda k: len(s.encoded(context[k])))
        if not context[largest]:
            break
        context[largest].pop()
    context['coverage'].update(records_included=len(context['records']), menus_included=len(context['history_menus']), stock_items_included=len(context['pantry']))
    context['coverage']['truncated'] = context['coverage']['details_truncated'] or total_actual>len(context['records']) or len(menus)>len(context['history_menus']) or len(usable)>len(context['pantry'])
    return context


def shopping_gaps(db, family_id, start, end, clock):
    grouped = {}
    menus = db.execute('SELECT * FROM menus WHERE family_id=? AND day BETWEEN ? AND ? ORDER BY day,meal', (family_id, start.isoformat(), end.isoformat())).fetchall()
    for menu in menus:
        details = db.execute('SELECT * FROM menu_ingredients WHERE menu_id=? ORDER BY position', (menu['id'],)).fetchall()
        if not details:
            details = [{'name': n, 'quantity': None, 'unit': '适量'} for n in json.loads(menu['ingredients'])]
        for ing in details:
            key = (name_key(ing['name']), ing['unit'])
            value = grouped.setdefault(key, {'name': ing['name'], 'unit': ing['unit'], 'quantity': Decimal(0), 'unknown_count': 0})
            if ing['quantity'] is None:
                value['unknown_count'] += 1
            else:
                value['quantity'] += Decimal(ing['quantity'])
    stock = snapshot(db, family_id, clock)
    by_name = defaultdict(list)
    for item in stock['items']:
        if item['status']=='available':
            by_name[name_key(item['name'])].append(item)
    unknown_requirements = {key[0] for key, v in grouped.items() if v['unknown_count']}
    result = []
    for (food, unit), value in sorted(grouped.items()):
        candidates = [i for i in by_name[food] if i['kind']=='raw']
        fresh = [i for i in candidates if not i['needs_reconfirmation']]
        exact = [i for i in fresh if i['unit']==unit and i['quantity'] is not None]
        known = sum((Decimal(i['quantity']) for i in exact), Decimal(0))
        required = value['quantity']
        uncertain_stock = len(exact)!=len(candidates)
        unknown_need = food in unknown_requirements or unit=='份'
        notes = []
        if unknown_need: notes.append('菜单用量未完整说明')
        if unit=='份': notes.append('份的规格可能不同，请核对实际量')
        if any(i['needs_reconfirmation'] for i in candidates): notes.append('食材记录需要重新确认')
        if any(i['quantity'] is None for i in fresh): notes.append('现有余量不明确')
        if any(i['quantity'] is not None and i['unit']!=unit for i in fresh): notes.append('库存与菜单单位不同，未换算')
        if by_name[food] and not candidates: notes.append('仅登记熟食，未按原料抵扣')
        if unknown_need or (uncertain_stock and known<required):
            category, buy = 'check', None
        elif known>=required and required>0:
            category, buy = 'enough', Decimal(0)
        else:
            category, buy = 'need_buy', required-known
            if not candidates: notes.append('当前清单未登记可抵扣原料，请按家中实际核对')
        result.append({'name': value['name'], 'unit': unit,
                       'quantity': str(required.normalize()) if required else None,
                       'unknown_count': value['unknown_count'],
                       'available_quantity': str(known.normalize()) if known else None,
                       'buy_quantity': str(buy.normalize()) if buy is not None else None,
                       'category': category, 'notes': notes})
    return {'items': result, 'inventory_revision': stock['version'],
            'note': '按已发布菜单与已确认原料估算；同名同单位先合并需求再抵扣一次，不换算单位或猜测同义词。读取清单不扣库存；买完后请确认家中实际总量。'}
