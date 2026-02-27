import json, app
cli = app.app.test_client()
payload = json.load(open('tests/payload_buck.json'))   # ← 新增

def test_explosion_flag():
    # 10 MOSFET dummy => 1024 combos > 512
    edges = [{'from':0,'to':1,'type':'mosfet'}]*10
    p = {'edges_on':edges,'edges_off':edges,'duty':0.5,
         'source':[0,-2],'output':[1,-2],'acAmp':1}
    r = cli.post('/calculate_average', json=p)
    d = json.loads(r.data)
    assert d['state_warn']  # should not be empty
