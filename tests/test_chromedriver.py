from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time

# Caminho para o ChromeDriver
CHROMEDRIVER_PATH = "C:\\Users\\Notebook\\Downloads\\chromedriver-win64 (1)\\chromedriver-win64\\chromedriver.exe"

# Configuração do serviço do ChromeDriver
service = Service(CHROMEDRIVER_PATH)

try:
    # Inicializar o WebDriver
    driver = webdriver.Chrome(service=service)
    print("ChromeDriver inicializado com sucesso.")

    # Abrir o Google
    driver.get("https://www.google.com")
    print("Google aberto com sucesso.")

    # Esperar 5 segundos
    time.sleep(5)

except Exception as e:
    print(f"Erro ao inicializar o ChromeDriver: {e}")

finally:
    # Fechar o navegador
    driver.quit()
    print("Navegador fechado.")