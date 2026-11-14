"""As regras do AGENTS.md que dá para conferir por código: se uma delas quebrar, o teste diz qual e onde.

Regra que mora só em texto é esquecida no primeiro PR de fora; aqui ela falha no CI.
"""
import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODULOS = sorted(RAIZ.glob("*.py"))
LOCAIS = {m.stem for m in MODULOS}


def _arvore(arq: Path) -> ast.Module:
    return ast.parse(arq.read_text(encoding="utf-8"), filename=str(arq))


def test_app_importa_so_biblioteca_padrao_sem_dependencia_externa():
    fora = []
    for arq in MODULOS:
        for no in ast.walk(_arvore(arq)):
            nomes = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                nomes = [no.module]
            for nome in nomes:
                topo = nome.split(".")[0]
                if topo not in sys.stdlib_module_names and topo not in LOCAIS and topo != "__future__":
                    fora.append(f"{arq.name}:{no.lineno} importa {nome}")
    assert not fora, "o app roda com `python3 app.py`, sem pip install:\n" + "\n".join(fora)


def test_sql_fora_do_nucleo_quebra_a_troca_de_banco():
    # nucleo.py é o único arquivo com SQL: trocar SQLite por Postgres tem de ser um arquivo só.
    fora = []
    for arq in MODULOS:
        if arq.name == "nucleo.py":
            continue
        for no in ast.walk(_arvore(arq)):
            if isinstance(no, ast.Attribute) and no.attr in {"execute", "executemany", "executescript"}:
                fora.append(f"{arq.name}:{no.lineno}")
            if isinstance(no, (ast.Import, ast.ImportFrom)) and "sqlite3" in ast.unparse(no):
                fora.append(f"{arq.name}:{no.lineno} importa sqlite3")
    assert not fora, "SQL fora do nucleo.py:\n" + "\n".join(fora)


def _variaveis_lidas(arq: Path) -> set[str]:
    """Nomes em MAIÚSCULAS lidos do ambiente: os.environ.get("X"), os.environ["X"], os.getenv("X")
    e o padrão `(os.environ.get(k) for k in ("A", "B"))`."""
    achadas = set()
    for funcao in ast.walk(_arvore(arq)):
        if not isinstance(funcao, (ast.FunctionDef, ast.Module)):
            continue
        fonte = ast.unparse(funcao) if isinstance(funcao, ast.FunctionDef) else ""
        for no in ast.walk(funcao):
            alvo = None
            if isinstance(no, ast.Call) and ast.unparse(no.func) in {"os.environ.get", "os.getenv", "os.environ.setdefault"}:
                alvo = no.args[0] if no.args else None
            elif isinstance(no, ast.Subscript) and ast.unparse(no.value) == "os.environ":
                alvo = no.slice
            if isinstance(alvo, ast.Constant) and isinstance(alvo.value, str):
                achadas.add(alvo.value)
            elif isinstance(alvo, ast.Name) and "for " + alvo.id + " in (" in fonte:
                achadas |= set(re.findall(r"['\"]([A-Z][A-Z0-9_]+)['\"]", fonte.split("for " + alvo.id + " in (", 1)[1].split(")")[0]))
    return achadas


def test_toda_variavel_de_ambiente_lida_pelo_codigo_esta_documentada_no_readme():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    lidas = set().union(*(_variaveis_lidas(a) for a in MODULOS))
    assert {"ADMIN_TOKEN", "WEBHOOK_SECRET", "CONEXOES_URL"} <= lidas, "o leitor de variáveis parou de enxergar o código"
    faltam = sorted(v for v in lidas if f"`{v}`" not in readme)
    assert not faltam, f"variáveis lidas pelo código e ausentes do README.md: {faltam}"


def test_mapa_do_agents_md_cita_todo_modulo_e_toda_pasta():
    agents = (RAIZ / "AGENTS.md").read_text(encoding="utf-8")
    pastas = [p.name + "/" for p in RAIZ.iterdir() if p.is_dir() and not p.name.startswith((".", "_")) and p.name != "data"]
    faltam = [m.name for m in MODULOS if f"`{m.name}`" not in agents] + [p for p in pastas if f"`{p}`" not in agents]
    assert not faltam, f"AGENTS.md não cita: {faltam} (o mapa do repositório é o que o próximo agente lê primeiro)"


def test_claude_md_aponta_para_o_agents_md_em_vez_de_copiar_regra():
    claude = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in claude and len(claude.splitlines()) < 40


def test_actions_do_ci_publico_fixadas_por_sha():
    soltas = []
    for wf in sorted((RAIZ / ".github" / "workflows").glob("*.yml")):
        for numero, linha in enumerate(wf.read_text(encoding="utf-8").splitlines(), start=1):
            m = re.search(r"uses:\s*([^\s#]+)", linha)
            if m and not re.search(r"@[0-9a-f]{40}$", m.group(1)):
                soltas.append(f"{wf.name}:{numero} {m.group(1)}")
    assert not soltas, "action sem SHA pode mudar por baixo do CI:\n" + "\n".join(soltas)


def test_python3_app_py_sobe_e_responde_saude(tmp_path):
    # Os outros testes montam o servidor por conta própria; este roda o comando do README. Um comentário de lint mal colado já
    # transformou o `.serve_forever()` em comentário: tudo verde e o app não atendia ninguém.
    import os
    import socket
    import subprocess
    import time
    import urllib.request

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    env = {**os.environ, "PORT": str(porta), "BIND": "127.0.0.1", "DATA_DIR": str(tmp_path), "ADMIN_TOKEN": "t", "WEBHOOK_SECRET": "t"}
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1) as r:
                    assert r.status == 200
                    return
            except OSError:
                if proc.poll() is not None:
                    raise AssertionError(proc.stderr.read().decode()[-500:]) from None
                time.sleep(0.1)
        raise AssertionError("python3 app.py não respondeu /saude em 5 s")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
