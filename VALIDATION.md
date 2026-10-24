# Validação — 24/10/2026

- 13 testes de backend aprovados: sessão, CSRF, histórico, pausa, exclusão mútua, recuperação após reinício, falhas de captura/API e formato da requisição com imagem.
- Integração HTTP com servidor Waitress real aprovada: inicialização em porta aleatória, bootstrap de sessão, cookie e consulta de estado.
- CSS compilado com Tailwind 4.3.3 e DaisyUI 5.7.50.
- JavaScript validado com node --check.
- Teste nativo do atalho não executado até o fim: o sandbox do Windows negou RegisterHotKey com erro 5. Teste marcado como skipped somente nessa condição.
- Nenhuma captura real foi enviada à OpenAI. Respostas da API simuladas nos testes; é necessário configurar uma chave e validar o fluxo completo localmente.
- A tentativa de teste visual com Edge headless não conseguiu iniciar o navegador neste ambiente. A interface não foi validada visualmente.
- Tauri/instalador não compilados: Rust/Cargo e Microsoft C++ Build Tools ausentes. WebView2 está instalado. Os fontes Rust e scripts de empacotamento estão incluídos, mas ainda exigem compilação e teste no Windows fora do sandbox.

O ZIP contém código-fonte e CSS compilado; não é um instalador ou executável final.
