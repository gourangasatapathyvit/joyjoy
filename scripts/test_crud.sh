#!/usr/bin/env bash
B=http://127.0.0.1:8080
A=(-s -m 25 -H "Authorization: Bearer dev-gateway-key-change-me" -H "X-User-Id: alice" -H "Content-Type: application/json")
PY='import sys,json;d=json.load(sys.stdin)'

echo "== 1. create user skill =="
curl "${A[@]}" -X POST "$B/v1/skills/save" -d '{"name":"mytest","content":"---\nname: mytest\ndescription: my crud test skill\n---\n# My Test\nDo X."}'; echo
echo "== 2. list user skills =="
curl "${A[@]}" "$B/v1/skills" | python3 -c "$PY;print([(s['name'],s['enabled']) for s in d['skills'] if s['scope']=='user'])"
echo "== 3. view mytest =="
curl "${A[@]}" "$B/v1/skills/content?name=mytest" | python3 -c "$PY;print('success',d['success'],'editable',d.get('editable'),'content_starts',repr(d.get('content','')[:25]))"
echo "== 4. disable mytest =="
curl "${A[@]}" -X POST "$B/v1/skills/toggle" -d '{"name":"mytest","enabled":false}'; echo
curl "${A[@]}" "$B/v1/skills" | python3 -c "$PY;print([(s['name'],s['enabled']) for s in d['skills'] if s['scope']=='user'])"
echo "== 5. delete mytest =="
curl "${A[@]}" -X POST "$B/v1/skills/delete" -d '{"name":"mytest"}'; echo
curl "${A[@]}" "$B/v1/skills" | python3 -c "$PY;print('user skills now:',[s['name'] for s in d['skills'] if s['scope']=='user'])"

echo "== 6. create user MCP (points at demo) =="
curl "${A[@]}" -X PUT "$B/v1/mcp/servers/myuser-demo" -d '{"command":"/home/gourangasatapathy/joyjoy/backend/.venv/bin/python","args":["/home/gourangasatapathy/joyjoy/backend/mcp_servers/joyjoy_demo.py"]}'; echo
curl "${A[@]}" "$B/v1/mcp/servers" | python3 -c "$PY;print([(s['name'],s['scope'],s['status'],s['tool_count']) for s in d['servers']])"
echo "== 7. reject editing a GLOBAL server =="
curl "${A[@]}" -X PUT "$B/v1/mcp/servers/joyjoy-demo" -d '{"command":"x"}'; echo
echo "== 8. toggle user MCP off =="
curl "${A[@]}" -X PATCH "$B/v1/mcp/servers/myuser-demo" -d '{"enabled":false}'; echo
curl "${A[@]}" "$B/v1/mcp/servers" | python3 -c "$PY;print([(s['name'],s['enabled'],s['status']) for s in d['servers'] if s['scope']=='user'])"
echo "== 9. delete user MCP =="
curl "${A[@]}" -X DELETE "$B/v1/mcp/servers/myuser-demo"; echo
curl "${A[@]}" "$B/v1/mcp/servers" | python3 -c "$PY;print('user servers now:',[s['name'] for s in d['servers'] if s['scope']=='user'])"

echo "== 10. write soul + read memory =="
curl "${A[@]}" -X POST "$B/v1/memory/write" -d '{"section":"soul","content":"You are Joy, warm and concise."}'; echo
curl "${A[@]}" "$B/v1/memory" | python3 -c "$PY;print('soul=',repr(d.get('soul')),'has_project_context=', 'project_context' in d)"
echo "DONE"
