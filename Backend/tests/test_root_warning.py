import json, app
cli = app.app.test_client()
payload = json.load(open('tests/payload_buck.json'))   # ← 新增

def test_warning_flag():
    bad = {**payload}
    bad['edges_on'][0]['gate'] = 99   # 无法判定 gate 节点
    rv = cli.post('/calculate_average', json=bad)
    data = json.loads(rv.data)
    assert 'mosfet_warn' in data
