import json, app
cli = app.app.test_client()

def test_basic_buck():
    payload = json.load(open('tests/payload_buck.json'))
    res = cli.post('/calculate_average', json=payload)
    j = json.loads(res.data)
    assert j['ssa_used'] is True
    assert j['tf'] 

