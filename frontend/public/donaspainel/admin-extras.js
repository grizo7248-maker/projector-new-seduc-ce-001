/* ============================================================
   Painel Admin — extras (SEDUC CE)
   Adiciona um botão "Limpar Cadastros" na página /donaspainel/cadastro
   sem precisar mexer no build React.
   ============================================================ */
(function () {
  var API = '/api';
  var BTN_ID = 'admin-extra-limpar-cadastros';

  function getToken() {
    var keys = ['donas_admin_token', 'donas_token', 'admin_token', 'token', 'authToken', 'jwt'];
    for (var i = 0; i < keys.length; i++) {
      var v = localStorage.getItem(keys[i]) || sessionStorage.getItem(keys[i]);
      if (v && v.length > 10) return v.replace(/^"|"$/g, '');
    }
    return null;
  }

  function injectStyles() {
    if (document.getElementById('admin-extras-css')) return;
    var s = document.createElement('style');
    s.id = 'admin-extras-css';
    s.textContent = ''
      + '#' + BTN_ID + '{display:inline-flex;align-items:center;gap:8px;'
      + 'padding:10px 16px;border-radius:10px;background:linear-gradient(180deg,#ef4444,#b91c1c);'
      + 'color:#fff;font-weight:600;font-size:13.5px;cursor:pointer;border:0;'
      + 'box-shadow:0 6px 14px rgba(220,38,38,.35);transition:transform .12s, box-shadow .12s;'
      + 'font-family:inherit;margin-left:8px}'
      + '#' + BTN_ID + ':hover{transform:translateY(-1px);box-shadow:0 8px 18px rgba(220,38,38,.45)}'
      + '#' + BTN_ID + ':disabled{opacity:.6;cursor:not-allowed;transform:none}'
      /* botão Exibir na linha do candidato */
      + '.adm-view-btn{display:inline-flex;align-items:center;justify-content:center;'
      + 'width:34px;height:34px;border-radius:8px;background:#eef0ff;color:#5b21b6;border:1px solid #d6dafd;'
      + 'cursor:pointer;margin-right:6px;font-size:15px;line-height:1;transition:transform .1s, background .1s}'
      + '.adm-view-btn:hover{background:#dde0ff;transform:translateY(-1px)}'
      /* modal de detalhes */
      + '#adm-details-back{position:fixed;inset:0;background:rgba(8,16,32,.55);'
      + 'display:flex;align-items:center;justify-content:center;z-index:2147483646;'
      + 'opacity:0;transition:opacity .18s ease;padding:16px;'
      + 'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}'
      + '#adm-details-back.show{opacity:1}'
      + '#adm-details{background:#fff;border-radius:14px;max-width:680px;width:100%;max-height:90vh;'
      + 'overflow:auto;box-shadow:0 24px 60px rgba(0,0,0,.35);transform:translateY(8px) scale(.98);'
      + 'transition:transform .22s cubic-bezier(.2,.8,.2,1)}'
      + '#adm-details-back.show #adm-details{transform:translateY(0) scale(1)}'
      + '#adm-details .adm-d-head{display:flex;align-items:center;justify-content:space-between;'
      + 'padding:18px 22px;background:linear-gradient(135deg,#5b21b6,#7c3aed);color:#fff;border-radius:14px 14px 0 0}'
      + '#adm-details .adm-d-head h3{margin:0;font-size:17px;font-weight:700}'
      + '#adm-details .adm-d-close{background:rgba(255,255,255,.2);border:0;color:#fff;width:32px;height:32px;'
      + 'border-radius:50%;cursor:pointer;font-size:16px;font-family:inherit;line-height:1}'
      + '#adm-details .adm-d-close:hover{background:rgba(255,255,255,.35)}'
      + '#adm-details .adm-d-body{padding:18px 22px 22px}'
      + '#adm-details .adm-d-section{margin-bottom:18px}'
      + '#adm-details .adm-d-section h4{margin:0 0 8px;color:#5b21b6;font-size:13px;font-weight:700;'
      + 'text-transform:uppercase;letter-spacing:.5px}'
      + '#adm-details .adm-d-row{display:flex;gap:8px;padding:6px 0;border-bottom:1px dashed #e5e7eb;font-size:14px}'
      + '#adm-details .adm-d-row:last-child{border-bottom:0}'
      + '#adm-details .adm-d-row b{min-width:170px;color:#374151;font-weight:600}'
      + '#adm-details .adm-d-row span{color:#111827;flex:1;word-break:break-word}'
      /* card do documento de identificação */
      + '#adm-details .adm-doc-card{display:flex;align-items:center;gap:12px;padding:10px 12px;'
      + 'border:1px solid #e5e7eb;border-radius:10px;background:#f9fafb;margin-top:6px}'
      + '#adm-details .adm-doc-thumb{width:48px;height:48px;border-radius:6px;border:1px solid #d1d5db;'
      + 'background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0;'
      + 'font-size:11px;font-weight:700;color:#6b7280}'
      + '#adm-details .adm-doc-thumb img{width:100%;height:100%;object-fit:cover}'
      + '#adm-details .adm-doc-meta{flex:1;min-width:0;font-size:13px}'
      + '#adm-details .adm-doc-meta strong{display:block;color:#111827;font-weight:600;font-size:13.5px;'
      + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
      + '#adm-details .adm-doc-meta small{color:#6b7280;font-size:12px}'
      + '#adm-details .adm-doc-actions{display:flex;gap:6px;flex-shrink:0}'
      + '#adm-details .adm-doc-btn{display:inline-flex;align-items:center;gap:5px;border:1px solid #d6dafd;'
      + 'background:#eef0ff;color:#5b21b6;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:13px;'
      + 'font-weight:600;font-family:inherit;transition:background .12s,transform .1s}'
      + '#adm-details .adm-doc-btn:hover{background:#dde0ff;transform:translateY(-1px)}'
      + '#adm-details .adm-doc-empty{color:#92400e;background:#fef3c7;padding:8px 10px;border-radius:8px;font-size:13px;margin-top:6px}'
      /* card Origem por dispositivo (dashboard) */
      + '#adm-funnel-devices{margin:18px 0 8px;width:100%;box-sizing:border-box;background:#fff;border:1px solid #eef0f6;border-radius:16px;padding:20px 22px;box-shadow:0 8px 24px rgba(17,24,39,.06);font-family:inherit}'
      + '#adm-funnel-devices .fd-title{font-size:13px;font-weight:800;color:#5b21b6;text-transform:uppercase;letter-spacing:.4px;margin:0 0 2px}'
      + '#adm-funnel-devices .fd-sub{font-size:12px;color:#6b7280;margin:0 0 14px}'
      + '#adm-funnel-devices .fd-head{display:grid;grid-template-columns:1fr 90px 90px;gap:12px;padding:0 12px 6px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.3px}'
      + '#adm-funnel-devices .fd-head span:not(:first-child){text-align:center}'
      + '#adm-funnel-devices .fd-row{display:grid;grid-template-columns:1fr 90px 90px;gap:12px;align-items:center;padding:10px 12px;border:1px solid #eef0f6;border-radius:10px;margin-bottom:8px;background:#fbfbfe}'
      + '#adm-funnel-devices .fd-row .fd-lbl{font-size:13.5px;font-weight:600;color:#374151}'
      + '#adm-funnel-devices .fd-pill{display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;padding:6px 0;border-radius:9999px}'
      + '#adm-funnel-devices .fd-desk{background:#eef2ff;color:#4338ca}'
      + '#adm-funnel-devices .fd-mob{background:#ecfdf5;color:#047857}';
    document.head.appendChild(s);
  }

  function isCadastroPage() {
    // Suporta tanto rota antiga (pathname) quanto HashRouter (location.hash)
    return /\/donaspainel\/cadastro(\b|$|\/)/.test(location.pathname)
        || /^#\/cadastro(\b|$|\/)/.test(location.hash);
  }
  function isInscricoesPage() {
    return location.pathname.indexOf('/donaspainel/inscri') === 0
        || location.hash.indexOf('#/inscri') === 0;
  }
  function isDashboardPage() {
    return /^#\/(dashboard)?$/.test(location.hash)
        || location.hash.indexOf('#/dashboard') === 0
        || /\/donaspainel\/?(#\/?)?$/.test(location.pathname + location.hash);
  }

  function ensureNoticeLib(cb) {
    if (window.IdecanConfirm) { cb(); return; }
    var s = document.createElement('script');
    s.src = '/assets/notice.js';
    s.onload = cb;
    document.head.appendChild(s);
  }

  function findActionsContainer() {
    // O React render coloca os botões "Buscar / Atualizar / Salvar .txt" próximos do header.
    // Vamos procurar pelo botão "Atualizar" (mais estável) e anexar do lado dele.
    var btns = document.querySelectorAll('button');
    var target = null;
    btns.forEach(function (b) {
      var t = (b.textContent || '').trim().toLowerCase();
      if (t === 'salvar .txt' || t.startsWith('salvar .txt')) target = b;
    });
    if (target && target.parentElement) return target.parentElement;
    // fallback: lado do Atualizar
    btns.forEach(function (b) {
      var t = (b.textContent || '').trim().toLowerCase();
      if (t === 'atualizar') target = b;
    });
    return target ? target.parentElement : null;
  }

  function findCountBadge() {
    // Procura por um elemento com "candidatos" e número (ex.: "80 cadastros")
    var nodes = document.querySelectorAll('strong, b, span, p');
    for (var i = 0; i < nodes.length; i++) {
      var t = (nodes[i].textContent || '').trim();
      if (/^\d+\s+cadastros?\.?$/i.test(t)) return nodes[i];
    }
    return null;
  }

  function handleAuthError(status) {
    // 401/403 — apenas avisa, sem redirecionar (usuário pode estar com cache de token velho)
    if (status === 401 || status === 403) {
      if (window.IdecanNotice) {
        IdecanNotice('Sua sessão precisa ser renovada. Saia e entre novamente no painel para continuar.', { title: 'Token expirado' });
      }
      return true;
    }
    return false;
  }

  function handleClick(btn) {
    var token = getToken();
    if (!token) {
      handleAuthError(401);
      return;
    }
    ensureNoticeLib(function () {
      window.IdecanConfirm(
        'Esta ação irá apagar TODOS os cadastros (candidatos) do banco. As inscrições NÃO serão afetadas. Continuar?',
        { title: 'Limpar todos os cadastros?', okLabel: 'Sim, limpar tudo', cancelLabel: 'Cancelar' }
      ).then(function (ok) {
        if (!ok) return;
        btn.disabled = true;
        var orig = btn.textContent;
        btn.textContent = 'Limpando…';
        // Tenta DELETE primeiro; se reverse-proxy bloquear (404/405/501) ou
        // se houver problema de método (alguns servidores), faz fallback para POST.
        function doRequest(method, url) {
          return fetch(API + url, {
            method: method,
            headers: { 'Authorization': 'Bearer ' + token }
          });
        }
        doRequest('DELETE', '/admin/cadastros').then(function (r) {
          if (r.ok) return r.json();
          // Fallback para POST quando DELETE é rejeitado pelo proxy
          if ([404, 405, 501, 502, 503].indexOf(r.status) !== -1) {
            return doRequest('POST', '/admin/cadastros/clear-all').then(function (r2) {
              if (!r2.ok) {
                if (handleAuthError(r2.status)) return null;
                throw new Error('HTTP ' + r2.status);
              }
              return r2.json();
            });
          }
          if (handleAuthError(r.status)) return null;
          throw new Error('HTTP ' + r.status);
        }).then(function (j) {
          if (!j) return;
          var n = (j && j.deleted) || 0;
          window.IdecanNotice(
            n + ' cadastro(s) removido(s) com sucesso. A página será recarregada.',
            { title: 'Limpeza concluída' }
          ).then(function () { location.reload(); });
        }).catch(function (e) {
          btn.disabled = false;
          btn.textContent = orig;
          window.IdecanNotice('Erro ao limpar cadastros: ' + e.message, { title: 'Falha' });
        });
      });
    });
  }


  // ---------- Lembrete de pagamento (e-mail para todos os inscritos) ----------
  var LEMBRETE_ID = 'admin-extra-lembrete-pagamento';
  function authFetch(method, url) {
    return fetch(API + url, { method: method, headers: { 'Authorization': 'Bearer ' + (getToken() || '') } })
      .then(function (r) {
        if (!r.ok) { handleAuthError(r.status); throw new Error('HTTP ' + r.status); }
        return r.json();
      });
  }
  function pollLembrete(btn, id) {
    authFetch('GET', '/admin/inscricoes/lembrete-pagamento/status/' + id).then(function (j) {
      var label = btn.querySelector('.lbl');
      if (j.status === 'enviando') {
        label.textContent = 'Enviando ' + (j.enviados + j.falhas) + '/' + j.total + '…';
        setTimeout(function () { pollLembrete(btn, id); }, 2000);
        return;
      }
      btn.disabled = false;
      label.textContent = 'Enviar lembrete de pagamento';
      alert('Lembrete de pagamento concluído.\n\nEnviados: ' + j.enviados + '\nFalhas: ' + j.falhas +
        (j.status === 'erro' ? '\n\nErro: ' + (j.erro || '') : ''));
    }).catch(function () { setTimeout(function () { pollLembrete(btn, id); }, 4000); });
  }
  function handleLembrete(btn) {
    if (!getToken()) { handleAuthError(401); return; }
    btn.disabled = true;
    authFetch('GET', '/admin/inscricoes/lembrete-pagamento/resumo').then(function (r) {
      if (r.em_andamento) { pollLembrete(btn, r.em_andamento.id); return; }
      if (!r.pendentes) {
        btn.disabled = false;
        alert(r.total ? 'Todos os ' + r.total + ' inscritos com e-mail já receberam o lembrete hoje (' + r.hoje + ').'
                      : 'Nenhum inscrito com e-mail encontrado.');
        return;
      }
      var msg = 'Enviar o e-mail "Último dia: sua inscrição está pendente de pagamento" para ' + r.pendentes +
        ' inscrito(s)?\n\nCada candidato recebe os dados da própria inscrição, o botão "Pagar inscrição" e o aviso de que o prazo termina hoje (' + r.hoje + ', às 23h59).' +
        (r.ja_enviados_hoje ? '\n\n' + r.ja_enviados_hoje + ' inscrito(s) que já receberam hoje serão pulados.' : '');
      if (!confirm(msg)) { btn.disabled = false; return; }
      return authFetch('POST', '/admin/inscricoes/lembrete-pagamento').then(function (job) { pollLembrete(btn, job.id); });
    }).catch(function (e) {
      btn.disabled = false;
      alert('Erro ao enviar lembrete: ' + e.message);
    });
  }
  function ensureLembreteButton() {
    var existing = document.getElementById(LEMBRETE_ID);
    if (!isInscricoesPage()) { if (existing) existing.remove(); return; }
    if (existing) return;
    var ref = null;
    document.querySelectorAll('button').forEach(function (b) {
      if ((b.textContent || '').trim().toLowerCase() === 'atualizar') ref = b;
    });
    if (!ref || !ref.parentElement) return;
    var btn = document.createElement('button');
    btn.id = LEMBRETE_ID;
    btn.type = 'button';
    btn.className = ref.className;
    btn.setAttribute('data-testid', 'btn-enviar-lembrete-pagamento');
    btn.style.cssText = 'background:#008d3c;color:#fff;border-color:#008d3c';
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg><span class="lbl">Enviar lembrete de pagamento</span>';
    btn.addEventListener('click', function () { handleLembrete(btn); });
    ref.parentElement.insertBefore(btn, ref);
  }

  function ensureButton() {
    // Limpa botão "Limpar Cadastros" se não estiver na página de cadastro
    if (!isCadastroPage()) {
      var existing = document.getElementById(BTN_ID);
      if (existing) existing.remove();
    } else if (!document.getElementById(BTN_ID)) {
      var container = findActionsContainer();
      if (container) {
        injectStyles();
        var btn = document.createElement('button');
        btn.id = BTN_ID;
        btn.type = 'button';
        btn.setAttribute('data-testid', 'btn-limpar-cadastros');
        btn.innerHTML = '<span aria-hidden="true">🗑</span><span>Limpar Cadastros</span>';
        btn.addEventListener('click', function () { handleClick(btn); });
        container.appendChild(btn);
      }
    }
    // Lógica que se aplica a múltiplas páginas do painel
    injectStyles();
    if (isCadastroPage()) {
      injectViewButtons();
      overrideExportButton();
    }
    ensureLembreteButton();
    if (isInscricoesPage()) {
      enrichInscriptionRows();
    }
    if (isDashboardPage()) {
      injectFunnelDevices();
    } else {
      removeFunnelDevices();
      _fdState.forKey = null;
    }
  }

  /* ====== Enriquece linhas da página de Inscrições: nome completo + vaga ====== */
  var _inscCache = null;
  var _inscCacheAt = 0;
  function fetchInscCache() {
    var now = Date.now();
    if (_inscCache && (now - _inscCacheAt) < 6000) return Promise.resolve(_inscCache);
    var token = getToken();
    if (!token) return Promise.resolve(null);
    return fetch(API + '/admin/inscriptions?limit=10000', {
      headers: { 'Authorization': 'Bearer ' + token }
    }).then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && (d.items || d.inscriptions)) || (Array.isArray(d) ? d : []);
      var byCpf = {};
      items.forEach(function (it) {
        var c = (it.cpf || '').replace(/\D/g, '');
        if (!byCpf[c]) byCpf[c] = [];
        byCpf[c].push(it);
      });
      _inscCache = byCpf; _inscCacheAt = now;
      return _inscCache;
    }).catch(function () { return null; });
  }

  function enrichInscriptionRows() {
    if (!isInscricoesPage()) return;
    fetchInscCache().then(function (byCpf) {
      if (!byCpf) return;
      injectInscStyles();
      // Estratégia simplificada: para cada DIV/SPAN folha com texto contendo "@",
      // sobe até achar um ancestor com CPF formatado e VALOR, e substitui o email pelo cargo.
      var candidates = document.querySelectorAll('div, span, p, td');
      candidates.forEach(function (el) {
        if (el.children.length) return;
        if (el.classList && el.classList.contains('adm-vaga-inline')) return;
        var t = (el.textContent || '').trim();
        if (!t || t.indexOf('@') < 0 || t.length > 100) return;
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)) return;
        // sobe DOM procurando o CPF e o valor
        var row = el.parentElement;
        for (var i = 0; i < 8 && row && row !== document.body; i++) {
          if (row.hasAttribute && row.hasAttribute('data-adm-enriched')) return;
          var rt = (row.textContent || '');
          var cpfMatch = rt.match(/\d{3}\.\d{3}\.\d{3}-\d{2}/);
          var valMatch = rt.match(/R\$\s*([\d.,]+)/);
          if (cpfMatch && valMatch && rt.length < 1500) {
            var cpfDigits = cpfMatch[0].replace(/\D/g, '');
            var inscs = byCpf[cpfDigits] || [];
            if (!inscs.length) return;
            var ins = inscs[0];
            if (inscs.length > 1) {
              var rowVal = parseFloat(valMatch[1].replace(/\./g,'').replace(',','.'));
              var found = inscs.find(function (x) { return Math.abs((x.valor || 0) - rowVal) < 0.5; });
              if (found) ins = found;
            }
            var cargo = (ins.cargo_titulo || ins.cargo_codigo || '').trim();
            if (cargo) {
              el.textContent = cargo;
              el.classList.add('adm-vaga-inline');
              row.setAttribute('data-adm-enriched', '1');
            }
            return;
          }
          row = row.parentElement;
        }
      });
    });
  }

  function injectInscStyles() {
    if (document.getElementById('adm-insc-css')) return;
    var s = document.createElement('style');
    s.id = 'adm-insc-css';
    s.textContent = ''
      + '.adm-full-name{font-weight:600;color:#1f2937;line-height:1.2;font-size:13.5px}'
      + '.adm-vaga{font-size:11.5px;color:#7c3aed;margin-top:3px;line-height:1.25;font-weight:500;letter-spacing:.2px}'
      + '.adm-vaga-inline{color:#7c3aed !important;font-weight:600 !important;font-size:11.5px !important;letter-spacing:.2px}';
    document.head.appendChild(s);
  }

  /* ====== Botão "Exibir" em cada linha (coluna AÇÕES) ====== */
  function injectViewButtons() {
    // A tabela do painel é construída com divs (flex/grid), não <tr>.
    // Estratégia: procurar elementos cujo texto seja um CPF formatado.
    // Subir no DOM até achar o container da "linha" (que tem a lixeira/SVG).
    var candidates = document.querySelectorAll('a, span, div, td');
    candidates.forEach(function (el) {
      if (el.children.length) return; // só folhas
      var t = (el.textContent || '').trim();
      if (!/^\d{3}\.\d{3}\.\d{3}-\d{2}$/.test(t)) return;
      var cpfDigits = t.replace(/\D/g, '');

      // sobe até achar uma linha que tenha um botão de lixeira (e ainda não tenha o nosso)
      var row = el;
      for (var i = 0; i < 8 && row && row !== document.body; i++) {
        if (row.querySelector('.adm-view-btn')) return; // já injetado
        // Procura um botão que tenha SVG/ícone (lixeira). Vamos detectar buttons dentro do row
        var btns = row.querySelectorAll('button');
        if (btns.length) {
          // achamos a linha
          var trashBtn = btns[btns.length - 1];
          // confirma que esta linha contém o CPF e não é o container inteiro
          var rowText = (row.textContent || '');
          if (rowText.indexOf(t) !== -1 && rowText.length < 500) {
            var viewBtn = document.createElement('button');
            viewBtn.type = 'button';
            viewBtn.className = 'adm-view-btn';
            viewBtn.setAttribute('data-testid', 'btn-exibir-cadastro');
            viewBtn.setAttribute('title', 'Exibir dados do cadastro');
            viewBtn.innerHTML = '👁';
            viewBtn.addEventListener('click', function (ev) {
              ev.preventDefault(); ev.stopPropagation();
              openDetailsModal(cpfDigits);
            });
            trashBtn.parentElement.insertBefore(viewBtn, trashBtn);
            return;
          }
        }
        row = row.parentElement;
      }
    });
  }

  /* ====== Modal de detalhes ====== */
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});
  }
  function fmtCPF(v) {
    var d = String(v||'').replace(/\D/g,'');
    if (d.length !== 11) return v||'';
    return d.slice(0,3)+'.'+d.slice(3,6)+'.'+d.slice(6,9)+'-'+d.slice(9);
  }
  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      var d = new Date(iso);
      return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    } catch (e) { return iso; }
  }

  function buildRows(pairs) {
    return pairs.map(function (p) {
      return '<div class="adm-d-row"><b>' + escapeHtml(p[0]) + '</b><span>' + escapeHtml(p[1] || '—') + '</span></div>';
    }).join('');
  }

  function fmtBytes(b) {
    b = Number(b) || 0;
    if (b < 1024) return b + ' B';
    if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
    return (b/(1024*1024)).toFixed(2) + ' MB';
  }

  /* Converte dataURL base64 → Blob (suporta arquivos grandes melhor que window.open(dataUrl)) */
  function dataUrlToBlob(dataUrl) {
    try {
      var parts = dataUrl.split(','); if (parts.length < 2) return null;
      var meta = parts[0]; var data = parts[1];
      var mime = (meta.match(/data:([^;]+)/) || [])[1] || 'application/octet-stream';
      var bin = atob(data);
      var arr = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      return new Blob([arr], { type: mime });
    } catch (e) { return null; }
  }

  function handleDocAction(action, fd, side) {
    if (!fd) return;
    var dataKey = side === 'verso' ? 'docArquivoVersoData' : 'docArquivoData';
    var nameKey = side === 'verso' ? 'docArquivoVersoNome' : 'docArquivoNome';
    if (!fd[dataKey]) return;
    var blob = dataUrlToBlob(fd[dataKey]);
    if (!blob) { alert('Não foi possível carregar o arquivo.'); return; }
    var url = URL.createObjectURL(blob);
    if (action === 'view') {
      var w = window.open(url, '_blank', 'noopener,noreferrer');
      if (!w && window.IdecanNotice) {
        IdecanNotice('Permita pop-ups para visualizar o documento.', { title: 'Bloqueado' });
      }
    } else if (action === 'download') {
      var a = document.createElement('a');
      a.href = url;
      a.download = fd[nameKey] || 'documento';
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(function(){ URL.revokeObjectURL(url); }, 60000);
  }

  function renderDocCard(fd, side){
    var prefix = side === 'verso' ? 'Verso' : 'Frente';
    var dataKey = side === 'verso' ? 'docArquivoVersoData' : 'docArquivoData';
    var nameKey = side === 'verso' ? 'docArquivoVersoNome' : 'docArquivoNome';
    var typeKey = side === 'verso' ? 'docArquivoVersoTipo' : 'docArquivoTipo';
    var sizeKey = side === 'verso' ? 'docArquivoVersoSize' : 'docArquivoSize';
    if (!fd[dataKey] && !fd[nameKey]) return '';
    var docTipo  = (fd.docTipo || 'Documento') + ' — ' + prefix;
    if (fd[dataKey] && fd[nameKey]) {
      var fileSize = fd[sizeKey] ? fmtBytes(fd[sizeKey]) : '';
      var isImg = (fd[typeKey] || '').indexOf('image/') === 0;
      var thumb = isImg
        ? '<img src="' + fd[dataKey] + '" alt="documento ' + prefix.toLowerCase() + '" />'
        : 'PDF';
      return '<div class="adm-doc-card" data-testid="modal-doc-card-' + side + '">' +
          '<div class="adm-doc-thumb">' + thumb + '</div>' +
          '<div class="adm-doc-meta">' +
            '<strong>' + escapeHtml(fd[nameKey]) + '</strong>' +
            '<small>' + escapeHtml(docTipo) + (fileSize ? ' · ' + fileSize : '') + '</small>' +
          '</div>' +
          '<div class="adm-doc-actions">' +
            '<button type="button" class="adm-doc-btn" data-doc-action="view" data-doc-side="' + side + '" data-testid="btn-view-doc-' + side + '">👁 Visualizar</button>' +
            '<button type="button" class="adm-doc-btn" data-doc-action="download" data-doc-side="' + side + '" data-testid="btn-download-doc-' + side + '">⬇ Baixar</button>' +
          '</div>' +
        '</div>';
    }
    if (fd[nameKey]) {
      return '<div class="adm-doc-empty" data-testid="modal-doc-meta-only-' + side + '">' +
        prefix + ' enviado: <b>' + escapeHtml(fd[nameKey]) + '</b>' +
        (fd[sizeKey] ? ' · ' + fmtBytes(fd[sizeKey]) : '') +
        ' — o arquivo não está mais armazenado em base64 (cadastro antigo).</div>';
    }
    return '';
  }

  function openDetailsModal(cpfDigits) {
    var token = getToken();
    if (!token) {
      if (window.IdecanNotice) IdecanNotice('Sessão expirada. Faça login novamente.', { title: 'Não autenticado' });
      return;
    }
    injectStyles();
    var back = document.createElement('div');
    back.id = 'adm-details-back';
    back.innerHTML = ''
      + '<div id="adm-details" data-testid="modal-detalhes-cadastro">'
      + '  <div class="adm-d-head"><h3>Carregando…</h3>'
      + '    <button class="adm-d-close" type="button" aria-label="Fechar">✕</button></div>'
      + '  <div class="adm-d-body"><p style="color:#6b7280;text-align:center">Buscando dados do candidato…</p></div>'
      + '</div>';
    document.body.appendChild(back);
    function close() {
      back.classList.remove('show');
      setTimeout(function () { back.remove(); }, 180);
    }
    back.querySelector('.adm-d-close').addEventListener('click', close);
    back.addEventListener('click', function (e) { if (e.target === back) close(); });
    requestAnimationFrame(function () { back.classList.add('show'); });

    fetch(API + '/admin/cadastros/' + cpfDigits + '/details', {
      headers: { 'Authorization': 'Bearer ' + token }
    }).then(function (r) {
      if (handleAuthError(r.status)) { close(); return null; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (doc) {
      if (!doc) return;
      var fd = doc.form_data || {};
      var head = back.querySelector('.adm-d-head h3');
      head.textContent = doc.nome || 'Candidato';
      var body = back.querySelector('.adm-d-body');
      var basic = buildRows([
        ['Nome', doc.nome],
        ['CPF', fmtCPF(doc.cpf)],
        ['E-mail', doc.email],
        ['Último concurso', doc.last_concurso],
        ['Inscrições', String(doc.inscricoes_count != null ? doc.inscricoes_count : 0)],
        ['Data do cadastro', fmtDate(doc.last_at || doc.created_at)],
      ]);
      var formHtml = '';
      if (fd && Object.keys(fd).length) {
        var personal = buildRows([
          ['Nome', fd.nome], ['Nome Social', fd.nomeSocial],
          ['Sexo', fd.sexo], ['Nascimento', fd.nascimento],
          ['Nacionalidade', fd.nacionalidade], ['Escolaridade', fd.escolaridade],
          ['Estado Civil', fd.estadoCivil], ['Nome da Mãe', fd.nomeMae],
        ]);
        var address = buildRows([
          ['CEP', fd.cep], ['Endereço', fd.endereco], ['Número', fd.numero],
          ['Complemento', fd.complemento], ['Bairro', fd.bairro],
          ['Cidade', fd.cidade], ['UF', fd.uf],
        ]);
        var contact = buildRows([
          ['Telefone 1', fd.tel1 + (fd.tel1Tipo ? ' (' + fd.tel1Tipo + ')' : '')],
          ['Telefone 2', fd.tel2 ? (fd.tel2 + (fd.tel2Tipo ? ' (' + fd.tel2Tipo + ')' : '')) : '—'],
          ['E-mail', fd.email], ['PCD', fd.pcd],
        ]);
        var docs = buildRows([
          ['RG', fd.rg], ['Data RG', fd.rgData],
          ['Órgão', fd.rgOrgao], ['UF', fd.rgUF],
          ['CPF', fmtCPF(fd.cpf || doc.cpf)],
        ]);
        /* === Documento de Identificação anexado (Frente + Verso) === */
        var docFrenteHtml = renderDocCard(fd, 'frente');
        var docVersoHtml  = renderDocCard(fd, 'verso');
        var docArquivoHtml = '';
        if (docFrenteHtml || docVersoHtml) {
          docArquivoHtml = docFrenteHtml + docVersoHtml;
        } else {
          docArquivoHtml = '<div class="adm-doc-empty" data-testid="modal-doc-empty">Nenhum documento de identificação anexado.</div>';
        }
        formHtml =
          '<div class="adm-d-section"><h4>Dados Pessoais</h4>' + personal + '</div>' +
          '<div class="adm-d-section"><h4>Endereço</h4>' + address + '</div>' +
          '<div class="adm-d-section"><h4>Contatos</h4>' + contact + '</div>' +
          '<div class="adm-d-section"><h4>Documentos</h4>' + docs + '</div>' +
          '<div class="adm-d-section"><h4>Documento de Identificação Anexado</h4>' + docArquivoHtml + '</div>';
      } else {
        formHtml = '<p style="color:#92400e;background:#fef3c7;padding:10px;border-radius:8px;font-size:13px">' +
                   '⚠️ Este cadastro foi criado antes da coleta de todos os campos. ' +
                   'Apenas os dados básicos estão disponíveis.</p>';
      }
      body.innerHTML =
        '<div class="adm-d-section"><h4>Resumo</h4>' + basic + '</div>' +
        formHtml;

      /* Bind click handlers para Visualizar/Baixar do documento */
      var docBtns = body.querySelectorAll('.adm-doc-btn');
      for (var bi = 0; bi < docBtns.length; bi++) {
        (function(btn){
          btn.addEventListener('click', function(){
            handleDocAction(btn.getAttribute('data-doc-action'), fd, btn.getAttribute('data-doc-side') || 'frente');
          });
        })(docBtns[bi]);
      }
    }).catch(function (e) {
      var body = back.querySelector('.adm-d-body');
      body.innerHTML = '<p style="color:#b91c1c">Erro ao carregar: ' + escapeHtml(e.message) + '</p>';
    });
  }

  /* ====== Sobrescreve "Salvar .txt" para baixar versão completa ====== */
  function overrideExportButton() {
    var btns = document.querySelectorAll('button:not([data-adm-export-bound])');
    btns.forEach(function (b) {
      var t = (b.textContent || '').trim().toLowerCase();
      if (t === 'salvar .txt' || t.startsWith('salvar .txt')) {
        b.setAttribute('data-adm-export-bound', '1');
        b.addEventListener('click', function (e) {
          e.preventDefault(); e.stopImmediatePropagation();
          var token = getToken();
          if (!token) { handleAuthError(401); return; }
          // baixa a versão completa
          fetch(API + '/admin/cadastros/export-full.txt', {
            headers: { 'Authorization': 'Bearer ' + token }
          }).then(function (r) {
            if (handleAuthError(r.status)) return null;
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.blob().then(function (blob) {
              var cd = r.headers.get('Content-Disposition') || '';
              var m = /filename="?([^"]+)"?/.exec(cd);
              var fn = (m && m[1]) || 'cadastros_completos.txt';
              var url = URL.createObjectURL(blob);
              var a = document.createElement('a');
              a.href = url; a.download = fn;
              document.body.appendChild(a); a.click(); a.remove();
              setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
            });
          }).catch(function (err) {
            if (window.IdecanNotice) IdecanNotice('Erro ao baixar: ' + err.message, { title: 'Falha' });
          });
        }, true);
      }
    });
  }

  // Observa o DOM (SPA — rotas mudam sem reload)
  var mo = new MutationObserver(function () { ensureButton(); enhanceDetailModal(); });

  /* ====== Customiza modal "Detalhes do candidato" do React Admin ======
   * Adiciona/renomeia a linha "Qr code gerado com a chave" ao final.
   * - Renomeia label "Pix Key Used" para "Qr code gerado com a chave"
   * - Esconde "Pix Key Used At" (timestamp interno)
   * - Se a inscrição NÃO tem pix_key_used (PIX ainda não gerado),
   *   injeta uma linha customizada com "aguardando gerar". */
  function enhanceDetailModal() {
    // Procura modal aberto pelo título
    var headings = document.querySelectorAll('h1, h2, h3, h4');
    var modal = null;
    for (var i = 0; i < headings.length; i++) {
      if ((headings[i].textContent || '').trim().indexOf('Detalhes do candidato') === 0) {
        modal = headings[i].closest('[role="dialog"], .dp-modal, .modal') ||
                headings[i].parentElement && headings[i].parentElement.parentElement;
        break;
      }
    }
    if (!modal) return;
    // Só processa quando o corpo do modal estiver populado
    var body = modal.querySelector('.dp-modal-body, .dp-detail-body');
    if (!body) return;
    var kvKeys = body.querySelectorAll('.kv-k');
    if (kvKeys.length === 0) return;  // dados ainda não chegaram

    /* Labels para ESCONDER */
    var hideLabels = {
      'Cargo Codigo': 1, 'Cargo Código': 1,
      'Finalized': 1, 'Finalized At': 1,
      'Pix Status At': 1,
      'Pix Key Used At': 1
    };
    /* Labels para RENOMEAR */
    var renameLabels = { 'Pix Key Used': 'Chave pix usada' };

    var foundUsed = false;
    var processedCount = 0;
    kvKeys.forEach(function (el) {
      var txt = (el.textContent || '').trim();
      if (renameLabels[txt]) {
        el.textContent = renameLabels[txt];
        foundUsed = true;
        processedCount++;
      } else if (hideLabels[txt]) {
        var row = el.closest('.dp-kv');
        if (row) row.style.display = 'none';
        processedCount++;
      }
    });

    // Só marca como processado se realmente fez alguma alteração
    if (processedCount === 0 && !foundUsed) return;
    if (modal.dataset.idcEnhanced === '1') return;
    modal.dataset.idcEnhanced = '1';

    // Remove a antiga linha "aguardando gerar" no header (bug anterior)
    var oldStrayRows = document.querySelectorAll('[data-testid="modal-chave-aguardando"]');
    oldStrayRows.forEach(function (n) { n.remove(); });

    // Se NÃO encontrou "Pix Key Used", PIX ainda não foi gerado (ou registro antigo)
    if (!foundUsed) {
      var lastSection = body.querySelector('.dp-section:last-of-type') || body;
      var lastGrid = lastSection.querySelector('.dp-kv-grid:last-of-type') || lastSection;
      var newKv = document.createElement('div');
      newKv.className = 'dp-kv flat';
      newKv.setAttribute('data-testid', 'modal-chave-aguardando');
      newKv.innerHTML =
        '<div class="kv-k">Chave pix usada</div>' +
        '<div class="kv-v" style="color:#9ca3af;font-style:italic">aguardando gerar</div>';
      lastGrid.appendChild(newKv);
    }
  }

  /* ====== Dashboard: card "Origem por dispositivo" (Desktop x Mobile) ====== */
  var _fdState = { loading: false, forKey: null };

  function findFunnelRow() {
    // menor elemento que contém tanto o Funil quanto a Atividade em tempo real
    // (é a linha de 2 colunas dentro da área de conteúdo, alinhada à direita da sidebar)
    var nodes = document.querySelectorAll('div,section');
    var best = null, bestLen = 1e9;
    for (var i = 0; i < nodes.length; i++) {
      var t = nodes[i].textContent || '';
      if (t.indexOf('Funil de convers') > -1 && t.indexOf('Atividade em tempo real') > -1) {
        if (t.length < bestLen) { bestLen = t.length; best = nodes[i]; }
      }
    }
    return best;
  }

  function funnelReady() {
    return (document.body.textContent || '').indexOf('Funil de convers') > -1
        && (document.body.textContent || '').indexOf('Acessos ao site') > -1;
  }

  function buildFunnelDevicesHtml(rows) {
    var html = ''
      + '<p class="fd-title">Origem por dispositivo</p>'
      + '<p class="fd-sub">Desktop vs Mobile em cada etapa do funil</p>'
      + '<div class="fd-head"><span>Etapa</span><span>Desktop</span><span>Mobile</span></div>';
    rows.forEach(function (r) {
      html += '<div class="fd-row">'
        + '<span class="fd-lbl">' + escapeHtml(r.label) + '</span>'
        + '<span class="fd-pill fd-desk">' + (r.desktop || 0) + '</span>'
        + '<span class="fd-pill fd-mob">' + (r.mobile || 0) + '</span>'
        + '</div>';
    });
    return html;
  }

  function renderFunnelDevices(rows) {
    var row = findFunnelRow();
    if (!row || !row.parentNode) return;
    var olds = document.querySelectorAll('#adm-funnel-devices');
    for (var i = 0; i < olds.length; i++) { olds[i].parentNode && olds[i].parentNode.removeChild(olds[i]); }
    var box = document.createElement('div');
    box.id = 'adm-funnel-devices';
    box.innerHTML = buildFunnelDevicesHtml(rows);
    row.parentNode.insertBefore(box, row.nextSibling);
  }

  function removeFunnelDevices() {
    var olds = document.querySelectorAll('#adm-funnel-devices');
    for (var i = 0; i < olds.length; i++) { olds[i].parentNode && olds[i].parentNode.removeChild(olds[i]); }
  }

  function injectFunnelDevices() {
    if (!isDashboardPage()) { _fdState.forKey = null; removeFunnelDevices(); return; }
    if (!funnelReady() || !findFunnelRow()) return; // dashboard ainda não renderizou
    var key = location.hash || location.pathname;
    if (_fdState.forKey === key && document.getElementById('adm-funnel-devices')) return;
    if (_fdState.loading) return;
    _fdState.loading = true;
    var tok = getToken();
    fetch(API + '/admin/dashboard/funnel-devices', {
      headers: tok ? { 'Authorization': 'Bearer ' + tok } : {}
    }).then(function (r) { return r.json(); }).then(function (rows) {
      _fdState.loading = false;
      if (Array.isArray(rows)) { _fdState.forKey = key; renderFunnelDevices(rows); }
    }).catch(function () { _fdState.loading = false; });
  }

  function start() {
    mo.observe(document.body, { childList: true, subtree: true });
    ensureButton();
    // também checa a cada mudança de URL (history API + HashRouter)
    var lastUrl = location.pathname + location.hash;
    setInterval(function () {
      var cur = location.pathname + location.hash;
      if (cur !== lastUrl) {
        lastUrl = cur;
        ensureButton();
      }
    }, 500);
    window.addEventListener('hashchange', ensureButton);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
  // expõe para debug e re-execução manual após mudanças assíncronas
  window.IdecanAdminExtras = {
    ensureButton: ensureButton,
    enrich: enrichInscriptionRows,
    enhanceDetailModal: enhanceDetailModal
  };
})();
