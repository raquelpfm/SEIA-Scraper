# Script para consultar o status de processos no SEIA INEMA

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd

# Configurações do sistema
LOGIN = ""
SENHA = ""
URL_LOGIN = "https://sistema.seia.ba.gov.br/login.xhtml"

# Processos a serem consultados
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
df_processos = pd.read_csv(os.path.join(_DIR, "script_processos.csv"), dtype=str)
processos = df_processos["numero_processo"].dropna().tolist()

# Iniciar navegador
options = Options()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)


def fechar_modal_aviso():
    try:
        botao_fechar = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#_dialogAlertaIndex a.ui-dialog-titlebar-close"))
        )
        botao_fechar.click()
        print("Modal de aviso fechado.")
    except Exception:
        print("Nenhum modal de aviso encontrado, prosseguindo...")
        
def fazer_login():
    driver.get(URL_LOGIN)
    fechar_modal_aviso()  # fechar aqui, logo após abrir o site

    campo_usuario = wait.until(
        EC.presence_of_element_located((By.ID, "j_username"))
    )
    campo_senha = driver.find_element(By.ID, "j_password")

    campo_usuario.send_keys(LOGIN)
    campo_senha.send_keys(SENHA)
    campo_senha.send_keys(Keys.RETURN)

    wait.until(EC.any_of(
        EC.url_contains("home"),
        EC.url_contains("erro=true")
    ))

    if "erro=true" in driver.current_url:
        raise Exception("Login falhou.")

def navegar_para_consulta():
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "accordionButton")))

    # Clica em "Processo" para expandir o submenu
    botao_processo = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//div[@class='accordionButton']//a[normalize-space()='Processo']"))
    )
    botao_processo.click()

    # Aguarda submenu expandir e clica em "Consultar Processo"
    link_consultar = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'accordionContent')]//a[normalize-space()='Consultar Processo']"))
    )
    link_consultar.click()

    # Aguarda o campo de busca estar disponível
    wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@id, 'formConsultarProcesso') and @type='text']"))
    )
    print("Tela de consulta carregada.")


def consultar_processo(numero):
    try:
        # Limpa a busca anterior
        botao_limpar = wait.until(
            EC.element_to_be_clickable((By.ID, "formConsultarProcesso:botao_limpar"))
        )
        botao_limpar.click()
        time.sleep(2)

        # Preenche o número do processo
        campo_busca = wait.until(
            EC.presence_of_element_located((By.XPATH, 
                "//input[contains(@id, 'formConsultarProcesso:j_idt') and @type='text']"
            ))
        )
        campo_busca.clear()
        campo_busca.send_keys(numero)

        # Clica em Consultar
        driver.find_element(By.ID, "formConsultarProcesso:botao_consultar").click()

        # Aguarda a tabela de resultados carregar
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 
                "#formConsultarProcesso\\:dataTableProcesso tbody tr"
            ))
        )

        # Captura o status (última coluna da primeira linha)
        status_element = driver.find_element(By.CSS_SELECTOR,
            "#formConsultarProcesso\\:dataTableProcesso tbody tr:first-child td:last-child div.ui-dt-c"
        )
        status = status_element.text.strip()

        print(f"{numero} -> {status}")
        return status

    except Exception as e:
        print(f"Erro no processo {numero}: {e}")
        return "ERRO"

def executar():
    resultados = []

    fazer_login()
    navegar_para_consulta()

    for processo in processos:
        status = consultar_processo(processo)
        resultados.append({
            "processo": processo,
            "status": status
        })
        time.sleep(2)

    df = pd.DataFrame(resultados)
    df.to_csv("resultado_processos.csv", index=False)
    print("Finalizado. Resultados salvos em resultado_processos.csv")


try:
    executar()
finally:
    driver.quit()