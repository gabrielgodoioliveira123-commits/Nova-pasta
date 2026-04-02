# Script para empacotar o programa em um único executável

Write-Host "Iniciando o processo de empacotamento..."

# Verificar se o PyInstaller está instalado
if (-Not (Get-Command "pyinstaller" -ErrorAction SilentlyContinue)) {
    Write-Host "PyInstaller não encontrado. Instalando..."
    pip install pyinstaller
}

# Caminho do arquivo principal
$mainFile = "E:\Projetos\1\Nova-pasta\src\main.py"

# Diretório de saída
$outputDir = "E:\Projetos\1\Nova-pasta\build"

# Comando para criar o executável
$command = "pyinstaller --onefile --distpath $outputDir --name ASTROCORE_INFINITY_ATOM $mainFile"

# Executar o comando
Invoke-Expression $command

Write-Host "Empacotamento concluído. O executável está localizado em $outputDir."