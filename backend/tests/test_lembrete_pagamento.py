# Tests for bulk payment reminder (lembrete de pagamento) endpoints + email HTML
import os, sys, time, uuid
import pytest, requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
load_dotenv('/app/frontend/.env')
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
REAL_CPFS = ['05058076292', '08757821160', '08052961580']
TEST_CPFS = ['52998224725', '11144477735']
JOB_IDS = []


@pytest.fixture(scope='module')
def token():
    r = requests.post(f'{BASE_URL}/api/admin/auth/login', json={'username': 'donas', 'password': 'Seinao10@@'})
    assert r.status_code == 200, r.text
    return r.json().get('token') or r.json().get('access_token')


@pytest.fixture(scope='module')
def H(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='module', autouse=True)
def safety(token):
    h = {'Authorization': f'Bearer {token}'}
    hoje = requests.get(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento/resumo', headers=h).json()['hoje']
    db.inscricoes.update_many({'cpf': {'$in': REAL_CPFS}}, {'$set': {'lembrete_enviado_dia': hoje}})
    db.inscricoes.delete_many({'cpf': {'$in': TEST_CPFS}})
    for cpf, nome in zip(TEST_CPFS, ['TESTE LEMBRETE UM', 'TESTE LEMBRETE DOIS']):
        db.inscricoes.insert_one({'id': str(uuid.uuid4()), 'cpf': cpf, 'nome': nome, 'email': 'delivered@resend.dev',
                                  'finalized': True, 'cargo_titulo': 'Professor de Matemática',
                                  'protocolo': '2026' + cpf[-6:], 'valor': 150, 'concurso': 'Concurso SEDUC/CE 2026'})
    yield hoje
    # Cleanup in teardown is done by a separate script after UI test (real flags kept until then)


def test_auth_required():
    for m, p in [('get', '/resumo'), ('post', ''), ('get', '/status/x')]:
        r = getattr(requests, m)(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento{p}')
        assert r.status_code in (401, 403), (p, r.status_code)


def test_resumo(H, safety):
    r = requests.get(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento/resumo', headers=H)
    assert r.status_code == 200
    d = r.json()
    assert d['total'] == 5 and d['ja_enviados_hoje'] == 3 and d['pendentes'] == 2, d
    assert d['hoje'] == safety and d['em_andamento'] is None


def test_status_404(H):
    r = requests.get(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento/status/nope', headers=H)
    assert r.status_code == 404


def test_send_job(H, safety):
    r = requests.post(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento', headers=H)
    assert r.status_code == 200, r.text
    job = r.json()
    JOB_IDS.append(job['id'])
    assert job['status'] == 'enviando' and job['total'] == 2
    for _ in range(40):
        s = requests.get(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento/status/{job["id"]}', headers=H).json()
        if s['status'] != 'enviando':
            break
        time.sleep(1)
    assert s['status'] == 'concluido' and s['enviados'] == 2 and s['falhas'] == 0, s
    for d in db.inscricoes.find({'cpf': {'$in': TEST_CPFS}}):
        assert d.get('lembrete_enviado_dia') == safety and d.get('lembrete_enviado_at')
    for d in db.inscricoes.find({'cpf': {'$in': REAL_CPFS}}):
        assert 'lembrete_enviado_at' not in d  # real ones not emailed


def test_no_duplicate(H):
    r = requests.get(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento/resumo', headers=H).json()
    assert r['pendentes'] == 0 and r['ja_enviados_hoje'] == 5
    j = requests.post(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento', headers=H).json()
    JOB_IDS.append(j['id'])
    assert j['total'] == 0
    time.sleep(2)
    s = requests.get(f'{BASE_URL}/api/admin/inscricoes/lembrete-pagamento/status/{j["id"]}', headers=H).json()
    assert s['status'] == 'concluido' and s['enviados'] == 0


def test_email_html():
    sys.path.insert(0, '/app/backend')
    from email_service import build_inscricao_email_html
    h = build_inscricao_email_html(nome='TESTE LEMBRETE UM', cpf='52998224725', protocolo='2026224725',
                                   cargo='Professor de Matemática', concurso='X', valor=150,
                                   base_url='https://x.com', lembrete_prazo='hoje, 16/01/2026, às 23h59 (horário de Brasília)')
    for s in ['TESTE LEMBRETE UM', 'Professor de Matem', '2026224725', 'R$ 150,00', 'pendente de pagamento',
              'o prazo termina hoje', 'Pagar inscrição',
              # APP_PUBLIC_URL (env) takes precedence over base_url by design
              f"{(os.environ.get('APP_PUBLIC_URL') or 'https://x.com').rstrip('/')}/pagamento-pix.html?cpf=52998224725"]:
        assert s in h, s
    assert ('529.982.247-25' in h) or ('52998224725' in h)
    n = build_inscricao_email_html(nome='A', cpf='52998224725', protocolo='1', cargo='C', concurso='X', valor=150,
                                   base_url='https://x.com')
    assert 'inscrição foi realizada com sucesso' in n and 'até dia' in n and '15/10/2026' in n
    assert 'o prazo termina hoje' not in n
