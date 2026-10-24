# ScrollAnswer (instalado como NetWatch)

O app instalado se chama **NetWatch** e abre num painel de monitoramento de rede com dados reais. O **®** do rodapé abre o ScrollAnswer; o botão "Voltar ao painel de rede" ou **Esc** retorna. Chaves e histórico ficam em `%LOCALAPPDATA%\NetWatch`; os de `%LOCALAPPDATA%\ScrollAnswer` são migrados automaticamente na primeira execução.

### IPs remotos de jogos e sites

No painel de rede, a seção **IPs remotos do aplicativo em primeiro plano** lista endpoints TCP/UDP observados nos últimos 30 segundos. Ao colocar um jogo ou navegador em primeiro plano, o app mostra seu executável e os IPs/portas das conexões desse processo e de seus filhos; ao voltar ao NetWatch, mantém a última seleção. No Firefox/Chrome e outros navegadores, as conexões de várias abas compartilham processos: **não é possível afirmar a qual site/aba pertence cada IP**. Alguns processos protegidos podem exigir execução com privilégios apropriados.

Para jogos que usam UDP sem conectar o socket, **execute o NetWatch como administrador** para ativar a captura UDP/IPv4 por sockets brutos nativos do Windows; não é necessário instalar Npcap nem outro driver. A captura examina somente cabeçalhos de pacotes nas interfaces IPv4 ativas e não armazena conteúdo dos pacotes. O painel informa quando faltam permissões. Conexões visíveis ao sistema continuam listadas mesmo sem administrador; a captura adicional de pacotes não cobre IPv6. Iniciar o app normalmente pelo menu Iniciar **não eleva privilégios**: use "Executar como administrador" no atalho se realmente precisar dessa captura. Conceda privilégios elevados somente se confia no app e nas páginas abertas na sua sessão.

Os IPs são **endpoints de rede, não identidades de pessoas**. Um jogo pode usar servidores/relays, um site pode usar CDNs e outras pessoas no mesmo site não têm conexões diretas com seu computador. Nem a captura por pacotes permite revelar IPs individuais que a arquitetura do serviço não expõe. O mapeamento de UDP usa porta local e processo: se vários processos compartilharem a mesma porta, a atribuição ambígua é ignorada. Não faz varredura, consultas externas de IP nem envia esses dados para terceiros.

Aplicativo Windows: **Scroll Lock → captura da janela ativa → API do Gemini (reservas opcionais: OpenAI, Claude) → resposta na janela Tauri**.

## Configuração rápida (Gemini)

1. Gere uma chave em [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (começa com `AIza` ou `AQ.`).
2. Rode `Configurar-chave.cmd`, cole a chave do Gemini e aperte Enter nas outras. O script confere se a chave e o modelo funcionam.
3. Reinicie o NetWatch e aperte Scroll Lock.

Modelo padrão: `gemini-3.5-flash` (`GEMINI_MODEL` / `gemini_model`). Ordem de tentativa: Gemini → OpenAI → GitHub Copilot (GitHub Models) → Claude, usando só os provedores com chave.

### Reserva: GitHub Copilot (GitHub Models, GPT Luna)

Crie um token fine-grained em github.com → Settings → Developer settings → Personal access tokens, com a permissão **Models: read**. Rode `Configurar-chave.cmd` e cole o token na pergunta do GitHub: o script consulta o catálogo e escolhe o modelo Luna com leitura de imagem (`github_model`; padrão `openai/gpt-6-luna`). O uso gratuito tem limite diário que depende do plano do Copilot. Quando um falha e outro responde, a resposta informa quem respondeu e por quê.

Python + Flask (MVC), SQLite e interface simples com DaisyUI/Tailwind. O backend é iniciado e encerrado pelo Tauri. Minimizar esconde a janela e deixa só um ícone, sem nome nem dica, na área de ícones ocultos da bandeja; o atalho continua ativo. Clique no ícone para reabrir; botão direito oferece "Abrir" e "Sair". Fechar encerra o aplicativo. Sem flash, som, prévia, mudança de foco ou notificações na captura. O aplicativo fica fora da barra de tarefas. Abra o atalho do menu Iniciar para restaurar a janela existente. Clicar no X encerra o aplicativo e o backend.

## Executar

Requisitos de desenvolvimento: Windows 10/11, Python 3.11+ com pip, Node.js 20+, Rust estável (MSVC), Microsoft C++ Build Tools e WebView2. Veja os [pré-requisitos oficiais do Tauri](https://v2.tauri.app/start/prerequisites/).

Na pasta deste projeto, em PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
$env:OPENAI_API_KEY = 'sua-chave'
npm.cmd run dev
```

A chave fica apenas no backend. Não a envie pelo chat. API tem cobrança própria; este aplicativo não envia para esta conversa do Codex e não utiliza automaticamente sua assinatura do ChatGPT.

Para configuração persistente, copie `config.example.json` para `%LOCALAPPDATA%\NetWatch\config.json`, preencha a chave no seu computador e reinicie. O arquivo contém a chave em texto simples: prefira a variável de ambiente se não quiser gravá-la. `OPENAI_API_KEY` e `OPENAI_MODEL` prevalecem sobre esse arquivo.

Modelo padrão: `gpt-4.1-mini`; altere para outro modelo com suporte a imagens disponível em sua conta. O prompt também pode ser alterado no JSON.

### Reserva: Claude (Anthropic)

Se a chamada à OpenAI falhar (rede, chave, saldo, modelo), a mesma captura é enviada ao Claude, e a resposta indica que veio da reserva e por quê. Gere uma chave em [console.anthropic.com](https://console.anthropic.com/) (começa com `sk-ant-`) e rode `Configurar-chave.cmd`, ou defina `ANTHROPIC_API_KEY` / `anthropic_api_key` no `config.json`. Modelo padrão: `claude-opus-5-5` (`ANTHROPIC_MODEL` / `anthropic_model`). Só com a chave do Claude, ele vira o provedor único. A chamada usa `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`): se o modelo recusar por política, a API tenta outro modelo Claude na mesma chamada.

## Usar

1. Abra o app e confira “Pronto para capturar”.
2. Coloque a janela desejada em primeiro plano.
3. Aperte **Scroll Lock / ScrLk** (alguns teclados exigem Fn).
4. Aguarde; a resposta aparece automaticamente no histórico. O app não rouba o foco.
5. Enquanto a API responde, novas capturas são ignoradas para evitar envios duplicados.

### Envio automático por e-mail

Cada resposta **concluída** pode ser enviada por SMTP, além de aparecer normalmente no histórico. A entrega ocorre uma vez por captura, sem repetição automática (para evitar mensagens duplicadas). Erros de envio aparecem abaixo da resposta e não apagam o texto retornado pela IA. Requer conexão, servidor SMTP e credenciais; o endereço de destino sozinho não permite enviar.

Configure localmente `%LOCALAPPDATA%\NetWatch\config.json` (copie `config.example.json`) ou defina variáveis de ambiente de mesmo nome em maiúsculas: `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`. Exemplo para quem usa a conta remetente no Gmail: `smtp_host` = `smtp.gmail.com`, `smtp_port` = `465`, `smtp_security` = `ssl`, `smtp_username` = endereço da conta, `smtp_password` = **senha de app** dessa conta; `smtp_from` pode ficar vazio (usa o usuário). Para servidor com STARTTLS, configure `smtp_security` = `starttls` e normalmente porta `587`. `smtp_to` já contém o destinatário solicitado no exemplo. Reinicie o app após configurar. **Não envie a senha pelo chat nem a inclua no código/instalador.** O arquivo local contém credenciais em texto simples; prefira variáveis de ambiente se necessário.

Sem configuração completa o painel indica que o e-mail está desativado. Envio real depende das credenciais do usuário e não é executado nos testes automatizados.

### Privacidade de monitores no Firefox

O Firefox não oferece aos sites a API `getScreenDetails()` para enumerar todas as telas. Para reduzir outros indícios quando a janela estiver numa tela secundária, a extensão opcional em `firefox-extension/` normaliza `screen.left/top`, `availLeft/availTop` e as coordenadas de janela, além de retornar `false` para `screen.isExtended` caso esse atributo esteja disponível. Ela roda no início de páginas HTTP(S), inclusive frames, somente no Firefox. **Não muda a quantidade de monitores do Windows, não cobre todos os sinais que um site pode usar e pode afetar sites que dependem de coordenadas reais.** Os outros monitores continuam utilizáveis.

Para experimentar: no Firefox, abra `about:debugging#/runtime/this-firefox`, clique **Carregar extensão temporária** e selecione `firefox-extension/manifest.json`. Recarregue os sites já abertos. Extensões temporárias deixam de funcionar após reiniciar o Firefox; instalação permanente depende da assinatura de extensões pela Mozilla. Remova-a nessa mesma tela se algum site apresentar problemas. A opção nativa `privacy.resistFingerprinting` em `about:config` também reduz dados de tela expostos a sites, mas pode alterar o comportamento de páginas; avalie separadamente.

“Pausar captura” desativa o envio por atalho. “Limpar histórico” remove respostas concluídas; solicitações pendentes continuam. Nenhum envio ocorre por temporizador. Os prints existem somente em memória e não são gravados no disco. O histórico textual fica em `%LOCALAPPDATA%\NetWatch\history.sqlite3`; a tela mostra as últimas 100 respostas.

A captura contém a **área visível da janela ativa**, incluindo barras do navegador e eventuais elementos sobrepostos. Não captura a página inteira com rolagem. Conteúdo protegido pode aparecer preto. O atalho é global: se outro programa estiver em primeiro plano, será ele que aparecerá na captura. O app informa quando Scroll Lock já está ocupado.

## Gerar instalador

```powershell
npm.cmd run build
```

O script gera um backend independente com PyInstaller, inclui CSS local e empacota com Tauri/NSIS. O instalador ficará em `src-tauri/target/release/bundle/nsis/`. A máquina de destino não precisa de Python ou Node. O instalador não é assinado.

## Arquitetura MVC

- `app/models.py`: persistência SQLite, recuperação de requisições interrompidas.
- `app/controllers.py`: rotas de estado, pausa, limpeza e sessão local.
- `app/templates/` + `app/static/`: Views; respostas renderizadas como texto, sem executar HTML.
- `app/services.py`: exclusão mútua, execução assíncrona, integração Responses API e mensagens de erro.
- `app/email.py`: envio SMTP autenticado e seguro das respostas concluídas.
- `app/windows.py`: RegisterHotKey (sem hook geral de teclado), captura em memória.
- `app/network.py`: tráfego, conexões do aplicativo ativo e captura UDP/IPv4 por sockets brutos do Windows com privilégios de administrador.
- `backend.py`: composição, DPI, configurações e servidor Waitress em loopback/porta aleatória.
- `src-tauri/`: janela nativa, inicialização e encerramento do backend.

O frontend usa uma sessão HttpOnly, token inicial de uso único e proteção CSRF; a chave OpenAI nunca vai para o JavaScript. Sem CDN em runtime. Requisições à OpenAI usam HTTPS, timeout de 120 segundos e `store: false`. Não há repetição automática de chamadas que possam gerar cobrança duplicada.

## Verificar

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
npm.cmd run css
```

Os testes não enviam imagens reais nem usam créditos. Para diagnóstico sem registrar o atalho: `python backend.py --no-hotkey` imprime uma URL local de acesso único.

Referências: [entrada de imagens na API](https://developers.openai.com/api/docs/guides/images-vision), [Tauri](https://v2.tauri.app/develop/configuration-files/), [DaisyUI](https://daisyui.com/docs/install/).
