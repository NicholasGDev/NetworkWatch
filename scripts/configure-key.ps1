$ErrorActionPreference = 'Stop'
Write-Host 'Configurar APIs do NetWatch'
Write-Host 'As chaves serao salvas no config.json local do aplicativo.'
Write-Host 'Deixe em branco (Enter) para manter a chave atual ou pular.'

function Read-Key($label) {
    $secure = Read-Host $label -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secure.Dispose() }
}

$geminiKey = Read-Key 'Chave do Gemini - principal (entrada oculta)'
$openaiKey = Read-Key 'Chave da OpenAI - reserva opcional (entrada oculta)'
$githubToken = Read-Key 'Token do GitHub (Copilot/GitHub Models, permissao models:read) - reserva opcional (entrada oculta)'
$claudeKey = Read-Key 'Chave do Claude/Anthropic - reserva opcional (entrada oculta)'
try {
    if (-not $geminiKey -and -not $openaiKey -and -not $githubToken -and -not $claudeKey) { throw 'Nenhuma chave informada. Nenhuma alteracao foi feita.' }
    if ($githubToken -and $githubToken -match '\s') { throw 'Token do GitHub com espacos. Nenhuma alteracao foi feita.' }
    if ($geminiKey -and $geminiKey -match '\s') { throw 'Chave Gemini com espacos. Nenhuma alteracao foi feita.' }
    if ($openaiKey -and -not $openaiKey.StartsWith('sk-')) { throw 'Formato de chave OpenAI inesperado. Nenhuma alteracao foi feita.' }
    if ($claudeKey -and -not $claudeKey.StartsWith('sk-ant-')) { throw 'Formato de chave Claude inesperado (deve comecar com sk-ant-). Nenhuma alteracao foi feita.' }
    $folder = if ($env:SCROLLANSWER_DATA_DIR) { $env:SCROLLANSWER_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'NetWatch' }
    $configPath = Join-Path $folder 'config.json'
    $config = if (Test-Path -LiteralPath $configPath) {
        Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    } else {
        [pscustomobject]@{ gemini_model = 'gemini-3.5-flash'; model = 'gpt-4.1-mini'; anthropic_model = 'claude-opus-5-5' }
    }
    if ($geminiKey) { $config | Add-Member -NotePropertyName 'gemini_api_key' -NotePropertyValue $geminiKey -Force }
    if ($openaiKey) { $config | Add-Member -NotePropertyName 'api_key' -NotePropertyValue $openaiKey -Force }
    if ($claudeKey) { $config | Add-Member -NotePropertyName 'anthropic_api_key' -NotePropertyValue $claudeKey -Force }
    if ($githubToken) {
        $config | Add-Member -NotePropertyName 'github_token' -NotePropertyValue $githubToken -Force
        # Consultar o catalogo nao gera cobranca; escolhe o modelo Luna com leitura de imagem.
        try {
            $catalog = Invoke-RestMethod -Uri 'https://models.github.ai/catalog/models' -TimeoutSec 20 -Headers @{
                Authorization = "Bearer $githubToken"; Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
            $luna = @($catalog | Where-Object { $_.id -match 'luna' -and $_.supported_input_modalities -contains 'image' } | Sort-Object id -Descending)
            if ($luna.Count) {
                $config | Add-Member -NotePropertyName 'github_model' -NotePropertyValue $luna[0].id -Force
                Write-Host "Token do GitHub OK. Modelo escolhido: $($luna[0].id)"
            } else {
                $visual = @($catalog | Where-Object { $_.publisher -match 'OpenAI' -and $_.supported_input_modalities -contains 'image' } | ForEach-Object { $_.id })
                Write-Host 'Atencao: nenhum modelo Luna com leitura de imagem no GitHub Models para este token.'
                Write-Host "Modelos OpenAI com imagem disponiveis: $($visual -join ', ')"
            }
        } catch {
            Write-Host "Atencao: nao foi possivel validar o token do GitHub: $($_.Exception.Message)"
        }
    }
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    Write-Host 'Chaves salvas.'
    if ($geminiKey) {
        # Listar modelos nao gera cobranca; so confirma a chave e o modelo.
        $model = if ($config.gemini_model) { $config.gemini_model } else { 'gemini-3.5-flash' }
        try {
            Invoke-RestMethod -Uri "https://generativelanguage.googleapis.com/v1beta/models/$model" -Headers @{ 'x-goog-api-key' = $geminiKey } -TimeoutSec 20 | Out-Null
            Write-Host "Chave do Gemini OK. Modelo $model disponivel."
        } catch {
            Write-Host "Atencao: nao foi possivel validar a chave/modelo do Gemini: $($_.Exception.Message)"
        }
    }
    Write-Host 'Reinicie o NetWatch para carregar a configuracao.'
    if ($env:GEMINI_API_KEY) { Write-Host 'Atencao: GEMINI_API_KEY tem prioridade sobre config.json.' }
    if ($env:OPENAI_API_KEY) { Write-Host 'Atencao: OPENAI_API_KEY tem prioridade sobre config.json.' }
    if ($env:GITHUB_TOKEN) { Write-Host 'Atencao: GITHUB_TOKEN tem prioridade sobre config.json.' }
    if ($env:ANTHROPIC_API_KEY) { Write-Host 'Atencao: ANTHROPIC_API_KEY tem prioridade sobre config.json.' }
} finally {
    $geminiKey = $null
    $openaiKey = $null
    $githubToken = $null
    $claudeKey = $null
}
