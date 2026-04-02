# Context Manager para dividir entradas grandes em partes menores
from typing import List

def split_input(input_text: str, max_length: int) -> List[str]:
    """
    Divide o texto de entrada em partes menores para evitar exceder o limite de contexto.

    Args:
        input_text (str): Texto de entrada.
        max_length (int): Comprimento máximo permitido.

    Returns:
        list: Lista de partes do texto.
    """
    parts: List[str] = []
    while len(input_text) > max_length:
        parts.append(input_text[:max_length])
        input_text = input_text[max_length:]
    parts.append(input_text)
    return parts

# Compactação do histórico de contexto
def compact_context(history: List[str], max_tokens: int) -> List[str]:
    """
    Compacta o histórico de contexto para reduzir o uso de tokens.

    Args:
        history (List[str]): Histórico de mensagens.
        max_tokens (int): Número máximo de tokens permitido.

    Returns:
        List[str]: Histórico compactado.
    """
    compacted = []
    tokens_used = 0

    for message in reversed(history):
        message_tokens = len(message)
        if tokens_used + message_tokens > max_tokens:
            break
        compacted.append(message)
        tokens_used += message_tokens

    return list(reversed(compacted))

# Exemplo de uso
def main():
    texto = """
    Este é um exemplo de texto muito longo que pode exceder o limite de contexto de um modelo.
    Vamos dividir este texto em partes menores para garantir que ele seja processado corretamente.
    """
    limite = 500  # Garantir consistência no limite de contexto
    partes = split_input(texto, limite)

    # Exemplo de compactação
    historico = ["Mensagem 1", "Mensagem 2", "Mensagem 3"]
    historico_compactado = compact_context(historico, 100)

    for i, parte in enumerate(partes):
        print(f"Parte {i + 1}:\n{parte}\n")

    print("Histórico compactado:", historico_compactado)

if __name__ == "__main__":
    main()