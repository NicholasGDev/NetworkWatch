/**
 * Controla a interface de respostas, captura e entrega por e-mail.
 *
 * @file
 */

/**
 * Obtém um elemento da página pelo identificador.
 *
 * @param {string} id Identificador do elemento.
 * @returns {HTMLElement|null} Elemento encontrado ou null.
 */
const $ = (id) => document.getElementById(id);
let paused = false;
let previous = '';
/**
 * Consulta a API local e inclui proteção CSRF em operações de alteração.
 * @param {string} path Caminho relativo à API.
 * @param {object} [body] Dados JSON da operação POST.
 * @returns {Promise<object>} Resposta JSON do backend.
 */
async function api(path, body) {
  const response = await fetch('/api/' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json',
      'X-CSRF-Token': document.querySelector('meta[name="csrf"]').content},
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error('Não foi possível acessar o serviço local. Reinicie o app se o problema continuar.');
  return response.json();
}
/**
 * Renderiza o histórico de respostas e o estado das entregas por e-mail.
 * @param {Array<object>} items Respostas devolvidas pelo backend.
 * @returns {void}
 */
function render(items) {
  const signature = JSON.stringify(items);
  if (signature === previous) return;
  previous = signature;
  $('count').textContent = items.length;
  $('empty').classList.toggle('hidden', items.length > 0);
  $('answers').replaceChildren(...items.map(item => {
    const card = document.createElement('article');
    card.className = 'card bg-base-100 border border-base-content/10';
    const body = document.createElement('div'); body.className = 'card-body p-5';
    const row = document.createElement('div'); row.className = 'flex justify-between items-center gap-3 mb-2';
    const date = document.createElement('span'); date.className = 'text-xs text-base-content/50';
    date.textContent = new Date(item.created).toLocaleString('pt-BR');
    const tag = document.createElement('span');
    tag.className = 'badge badge-sm ' + ({done:'badge-success', error:'badge-error', pending:'badge-warning'}[item.status]);
    tag.textContent = {done:'Respondido', error:'Erro', pending:'Analisando…'}[item.status];
    row.append(date, tag);
    const text = document.createElement('p'); text.className = 'whitespace-pre-wrap break-words leading-relaxed text-sm';
    text.textContent = item.status === 'pending' ? 'Aguardando a resposta da IA…' : item.answer;
    body.append(row, text);
    if (item.email_status !== 'disabled') {
      const delivery = document.createElement('p');
      delivery.className = 'text-xs ' + (item.email_status === 'error' ? 'text-error' :
        item.email_status === 'sent' ? 'text-success' : 'text-base-content/50');
      delivery.textContent = item.email_status === 'sent' ? 'E-mail enviado.' :
        item.email_status === 'sending' ? 'Enviando e-mail…' : item.email_error;
      body.append(delivery);
    }
    card.append(body); return card;
  }));
}
/**
 * Atualiza estado e histórico e agenda a próxima consulta local.
 *
 * @returns {Promise<void>}
 */
async function refresh() {
  try {
    const {status: s, answers} = await api('state');
    paused = s.paused;
    $('pause').disabled = false;
    $('pause').textContent = paused ? 'Retomar captura' : 'Pausar captura';
    $('status').textContent = s.busy ? 'Analisando captura…' : paused ? 'Captura pausada' :
      !s.configured ? 'Configure sua chave da API' : !s.hotkey_ready ? 'Atalho indisponível' : 'Pronto para capturar';
    $('light').className = 'badge badge-xs ' + (s.configured && s.hotkey_ready && !paused ? 'badge-success' : 'badge-warning');
    $('model').textContent = 'Modelo: ' + s.model;
    $('email').textContent = s.email_config_error || (s.email_configured ?
      'E-mail ativo: respostas concluídas são enviadas por SMTP.' :
      'E-mail desativado: configure SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD e SMTP_TO.');
    $('error').textContent = s.hotkey_error || (!s.configured ? 'Defina OPENAI_API_KEY ou configure config.json conforme o README e reinicie.' : '');
    $('error').classList.toggle('hidden', !$('error').textContent);
    render(answers);
  } catch (error) {
    $('status').textContent = 'Serviço desconectado';
    $('light').className = 'badge badge-error badge-xs';
    $('pause').disabled = true;
    $('error').textContent = error.message; $('error').classList.remove('hidden');
  } finally { setTimeout(refresh, 1000); }
}
/**
 * Executa uma ação da interface e exibe falhas no painel.
 * @param {string} path Rota da ação.
 * @param {object} body Corpo JSON da solicitação.
 * @returns {Promise<void>}
 */
async function action(path, body) {
  try { await api(path, body); }
  catch (error) { $('error').textContent = error.message; $('error').classList.remove('hidden'); }
}
// Esc volta para o painel de rede.
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') location.href = '/'; });
$('pause').onclick = () => action('pause', {paused: !paused});
$('clear').onclick = () => { if (confirm('Apagar as respostas concluídas deste computador?')) action('clear', {}); };
refresh();
