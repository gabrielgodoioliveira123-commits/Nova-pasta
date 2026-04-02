from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
import os
from context_manager import split_input, compact_context

# Configuração do serviço para o ChromeDriver
caminho_chromedriver = "C:\\Users\\Notebook\\Downloads\\chromedriver-win64 (1)\\chromedriver-win64\\chromedriver.exe"
service = Service(caminho_chromedriver)

# Adicionar mensagens de log para depuração
print(f"Usando ChromeDriver no caminho: {caminho_chromedriver}")

def iniciar_driver() -> WebDriver:
    """Inicializa e retorna uma instância do WebDriver."""
    driver = webdriver.Chrome(service=service)
    if not isinstance(driver, WebDriver):
        raise TypeError("Erro ao inicializar o WebDriver: Tipo inesperado")
    return driver

def buscar_google(driver: WebDriver, termo: str):
    """Realiza uma busca no Google pelo termo especificado."""
    partes = split_input(termo, 500)  # Ajustar limite de contexto para 500

    # Exemplo de histórico de contexto
    historico = ["Busca anterior 1", "Busca anterior 2"]
    historico_compactado = compact_context(historico, 100)
    print("Histórico compactado:", historico_compactado)

    for parte in partes:
        driver.get("https://www.google.com")
        search_box: WebElement = driver.find_element(By.NAME, "q")
        search_box.send_keys(parte)
        search_box.send_keys(Keys.RETURN)

def main():
    driver: WebDriver | None = None
    try:
        driver = iniciar_driver()
        buscar_google(driver, "Exemplo de automação com Selenium")
    except Exception as e:
        print(f"Erro durante a execução do Selenium: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()