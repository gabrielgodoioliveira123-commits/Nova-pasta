# ASTROCORE INFINITY ATOM - Main Module

# Este é o ponto de entrada principal do sistema.
# Ele será responsável por inicializar os módulos principais e gerenciar o fluxo do programa.

import sys
import os

# Adicionando o caminho do diretório sandbox ao sys.path para resolver importações
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../sandbox'))

from core import initialize_core
from modules.diagnostics import run_diagnostics
from modules.gui import launch_gui
from context_manager import split_input, compact_context

# Configuração para o Codex
project_root_markers = []  # Força o Codex a tratar o diretório atual como raiz
project_doc_max_bytes = 4096  # Limita o tamanho do AGENTS.md no contexto inicial

def main():
    print("Bem-vindo ao ASTROCORE INFINITY ATOM")
    initialize_core()
    run_diagnostics()
    launch_gui()

    texto = """
    Insira aqui o texto ou entrada que será enviada ao modelo.
    Certifique-se de que ele seja processado em partes menores.
    """
    limite = 500  # Defina o limite de contexto do modelo
    partes = split_input(texto, limite)

    # Exemplo de histórico de contexto
    historico = ["Entrada anterior 1", "Entrada anterior 2"]
    historico_compactado = compact_context(historico, 100)
    print("Histórico compactado:", historico_compactado)

    for i, parte in enumerate(partes):
        print(f"Processando parte {i + 1}:")
        # Aqui você pode enviar cada parte ao modelo
        # Exemplo: resultado = modelo.processar(parte)
        print(parte)

if __name__ == "__main__":
    main()