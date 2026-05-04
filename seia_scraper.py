import threading
import time
from pathlib import Path

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ─────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────

LOGIN = ""
SENHA = ""
URL_LOGIN = "https://sistema.seia.ba.gov.br/login.xhtml"

TIMEOUT = 15


# ─────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────

def criar_driver():
    options = Options()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, TIMEOUT)

    return driver, wait


# ─────────────────────────────────────────────
# SEIA
# ─────────────────────────────────────────────

def fechar_modal_aviso(driver, wait):
    try:
        botao_fechar = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#_dialogAlertaIndex a.ui-dialog-titlebar-close")
            )
        )
        botao_fechar.click()
        return True
    except Exception:
        return False


def fazer_login(driver, wait, login, senha, callback=None):
    driver.get(URL_LOGIN)

    if callback:
        callback("Abrindo portal SEIA...")

    fechar_modal_aviso(driver, wait)

    campo_usuario = wait.until(
        EC.presence_of_element_located((By.ID, "j_username"))
    )

    campo_senha = driver.find_element(By.ID, "j_password")

    campo_usuario.clear()
    campo_usuario.send_keys(login)

    campo_senha.clear()
    campo_senha.send_keys(senha)
    campo_senha.send_keys(Keys.RETURN)

    wait.until(
        EC.any_of(
            EC.url_contains("home"),
            EC.url_contains("erro=true")
        )
    )

    if "erro=true" in driver.current_url:
        raise Exception("Login falhou.")

    if callback:
        callback("✓ Login realizado com sucesso")


def navegar_para_consulta(driver, wait, callback=None):
    if callback:
        callback("Abrindo tela de consulta...")

    wait.until(
        EC.presence_of_element_located((By.CLASS_NAME, "accordionButton"))
    )

    botao_processo = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH,
             "//div[@class='accordionButton']//a[normalize-space()='Processo']")
        )
    )

    botao_processo.click()

    link_consultar = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH,
             "//div[contains(@class,'accordionContent')]//a[normalize-space()='Consultar Processo']")
        )
    )

    link_consultar.click()

    wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//input[contains(@id, 'formConsultarProcesso') and @type='text']"
            )
        )
    )

    if callback:
        callback("✓ Tela de consulta carregada")


def consultar_processo(driver, wait, numero):
    """
    Pesquisa o processo na listagem e retorna um dict com:
      - status
      - nome_empreendimento
      - email
    Abre o painel de detalhes e extrai as informações adicionais.
    """
    resultado = {
        "status": "ERRO",
        "nome_empreendimento": "",
        "email": "",
    }

    try:
        # ── 1. Limpar busca anterior ──────────────────────────────────────
        botao_limpar = wait.until(
            EC.element_to_be_clickable(
                (By.ID, "formConsultarProcesso:botao_limpar")
            )
        )
        botao_limpar.click()
        time.sleep(1.5)

        # ── 2. Digitar número e consultar ─────────────────────────────────
        campo_busca = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//input[contains(@id, 'formConsultarProcesso:j_idt') and @type='text']"
                )
            )
        )
        campo_busca.clear()
        campo_busca.send_keys(numero)

        driver.find_element(
            By.ID,
            "formConsultarProcesso:botao_consultar"
        ).click()

        # ── 3. Aguardar resultado na tabela ───────────────────────────────
        wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "#formConsultarProcesso\\:dataTableProcesso tbody tr"
                )
            )
        )

        # ── 4. Ler status da listagem ─────────────────────────────────────
        status_element = driver.find_element(
            By.CSS_SELECTOR,
            "#formConsultarProcesso\\:dataTableProcesso tbody tr:first-child td:last-child div.ui-dt-c"
        )
        resultado["status"] = status_element.text.strip()

        # ── 5. Abrir detalhes do processo ─────────────────────────────────
        #   Clica no link/botão da primeira linha da tabela para abrir o painel
        link_processo = wait.until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    "#formConsultarProcesso\\:dataTableProcesso tbody tr:first-child td:first-child a"
                )
            )
        )
        link_processo.click()

        # Aguarda o painel de detalhes aparecer
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".ui-dialog[id*='DialogDetalharProcesso'], "
                                  ".ui-dialog[id*='dialogDetalharProcesso'], "
                                  "div[id*='DialogDetalharProcesso']")
            )
        )
        time.sleep(1)

        # ── 6. Extrair nome do empreendimento ─────────────────────────────
        #   Na aba "Atos e Dados Gerais" / painel principal, o nome aparece
        #   como texto numa célula ou label específico.
        nome = _extrair_nome_empreendimento(driver)
        resultado["nome_empreendimento"] = nome

        # ── 7. Navegar para aba de dados gerais e extrair e-mail ──────────
        email = _extrair_email(driver, wait)
        resultado["email"] = email

        # ── 8. Fechar painel de detalhes ──────────────────────────────────
        _fechar_painel_detalhes(driver, wait)

    except Exception as e:
        # Tenta fechar o painel caso tenha ficado aberto
        try:
            _fechar_painel_detalhes(driver, wait)
        except Exception:
            pass

        resultado["status"] = "ERRO"

    return resultado


# ─────────────────────────────────────────────
# FUNÇÕES AUXILIARES DE EXTRAÇÃO
# ─────────────────────────────────────────────

def _extrair_nome_empreendimento(driver):
    """
    Tenta extrair o nome do empreendimento do painel de detalhes do processo.
    O SEIA exibe essa informação num label/célula identificada por 'nomeEmpreendimento'
    ou dentro de uma tabela de dados gerais do processo.
    Tenta múltiplas estratégias para maior robustez.
    """
    estrategias = [
        # Estratégia 1: campo com id ou name contendo 'nomeEmpreendimento'
        lambda d: d.find_element(
            By.XPATH,
            "//*[contains(@id,'nomeEmpreendimento') or contains(@name,'nomeEmpreendimento')]"
        ).text.strip(),

        # Estratégia 2: label "Nome / Razão Social" seguido do valor
        lambda d: d.find_element(
            By.XPATH,
            "//td[contains(normalize-space(),'Nome') and contains(normalize-space(),'Razão')]/following-sibling::td[1]"
        ).text.strip(),

        # Estratégia 3: linha da tabela com rótulo "Empreendimento"
        lambda d: d.find_element(
            By.XPATH,
            "//td[normalize-space()='Empreendimento']/following-sibling::td[1]"
        ).text.strip(),

        # Estratégia 4: célula genérica de nome dentro do dialog de detalhes
        lambda d: d.find_element(
            By.XPATH,
            "//div[contains(@id,'DetalharProcesso') or contains(@id,'detalharProcesso')]"
            "//td[contains(normalize-space(.),'Nome')]/following-sibling::td[1]"
        ).text.strip(),
    ]

    for fn in estrategias:
        try:
            valor = fn(driver)
            if valor:
                return valor
        except Exception:
            continue

    return ""


def _extrair_email(driver, wait):
    """
    Navega para a aba 'Atos e Dados Gerais' (ou 'Dados Gerais') dentro do
    painel de detalhes e extrai o e-mail do responsável/requerente.
    """
    # ── Tenta clicar na aba 'Atos e Dados Gerais' ───────────────────────
    seletores_aba = [
        "//a[normalize-space()='Atos e Dados Gerais']",
        "//a[normalize-space()='Dados Gerais']",
        "//span[normalize-space()='Atos e Dados Gerais']",
        "//li[contains(@class,'ui-tabs-header')]//a[contains(normalize-space(),'Dados')]",
    ]

    aba_clicada = False
    for xpath in seletores_aba:
        try:
            aba = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            aba.click()
            time.sleep(1)
            aba_clicada = True
            break
        except Exception:
            continue

    # ── Extrai o e-mail ──────────────────────────────────────────────────
    estrategias_email = [
        # Estratégia 1: campo com id/name contendo 'email' (case-insensitive via translate)
        lambda d: d.find_element(
            By.XPATH,
            "//*[contains(translate(@id,'EMAIL','email'),'email') "
            "or contains(translate(@name,'EMAIL','email'),'email')]"
        ).text.strip(),

        # Estratégia 2: label 'E-mail' / 'Email' seguido da célula vizinha
        lambda d: d.find_element(
            By.XPATH,
            "//td[contains(normalize-space(),'E-mail') or contains(normalize-space(),'Email')]"
            "/following-sibling::td[1]"
        ).text.strip(),

        # Estratégia 3: texto que parece um e-mail (contém '@') dentro do dialog
        lambda d: d.find_element(
            By.XPATH,
            "//div[contains(@id,'DetalharProcesso') or contains(@id,'detalharProcesso')]"
            "//*[contains(text(),'@')]"
        ).text.strip(),

        # Estratégia 4: dentro de qualquer elemento com 'role' dentro do dialog
        lambda d: d.find_element(
            By.XPATH,
            "//td[normalize-space()='E-mail']/following-sibling::td[1]"
        ).text.strip(),
    ]

    for fn in estrategias_email:
        try:
            valor = fn(driver)
            if valor and "@" in valor:
                return valor
        except Exception:
            continue

    return ""


def _fechar_painel_detalhes(driver, wait):
    """
    Fecha o painel/dialog de detalhes do processo.
    Tenta clicar no botão de fechar (×) do dialog.
    """
    seletores_fechar = [
        ".ui-dialog[id*='DialogDetalharProcesso'] a.ui-dialog-titlebar-close",
        ".ui-dialog[id*='dialogDetalharProcesso'] a.ui-dialog-titlebar-close",
        "a.ui-dialog-titlebar-close",
    ]

    for seletor in seletores_fechar:
        try:
            botao = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, seletor))
            )
            botao.click()
            time.sleep(0.8)
            return
        except Exception:
            continue


# ─────────────────────────────────────────────
# EXECUÇÃO
# ─────────────────────────────────────────────

def executar_consulta(login, senha, csv_entrada, csv_saida, callback_log, callback_fim):

    try:
        df = pd.read_csv(csv_entrada, dtype=str)
    except Exception as e:
        callback_log(f"✗ Erro ao abrir CSV: {e}")
        callback_fim(False)
        return

    if "numero_processo" not in df.columns:
        callback_log("✗ CSV inválido: coluna 'numero_processo' não encontrada")
        callback_fim(False)
        return

    processos = (
        df["numero_processo"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    if not processos:
        callback_log("✗ Nenhum processo encontrado no CSV")
        callback_fim(False)
        return

    callback_log(f"{len(processos)} processo(s) carregado(s)")

    resultados = []

    driver, wait = criar_driver()

    try:
        fazer_login(driver, wait, login, senha, callback_log)
        navegar_para_consulta(driver, wait, callback_log)

        total = len(processos)

        for i, processo in enumerate(processos, 1):
            callback_log(f"[{i}/{total}] Consultando {processo}")

            dados = consultar_processo(driver, wait, processo)

            resultados.append({
                "processo": processo,
                "status": dados["status"],
                "nome_empreendimento": dados["nome_empreendimento"],
                "email": dados["email"],
            })

            if dados["status"] == "ERRO":
                callback_log(f"  ✗ Erro na consulta")
            else:
                nome_log = dados["nome_empreendimento"] or "—"
                email_log = dados["email"] or "—"
                callback_log(f"  ✓ {dados['status']}")
                callback_log(f"    Empreendimento: {nome_log}")
                callback_log(f"    E-mail: {email_log}")

            time.sleep(1)

        pd.DataFrame(resultados).to_csv(csv_saida, index=False, encoding="utf-8-sig")

        callback_log("")
        callback_log("=" * 55)
        callback_log("CONSULTA FINALIZADA")
        callback_log(f"Arquivo salvo: {csv_saida}")
        callback_log("=" * 55)

        callback_fim(True)

    except Exception as e:
        callback_log(f"✗ Erro fatal: {e}")
        callback_fim(False)

    finally:
        driver.quit()


# ─────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────

def iniciar_interface():

    BG = "#0f1117"
    PAINEL = "#1a1d27"
    BORDA = "#2a2d3e"
    ACENTO = "#4f8ef7"
    SUCESSO = "#3ecf8e"
    ERRO_C = "#f76f6f"
    TEXTO = "#e8eaf0"
    SUBTEXTO = "#7b7f96"
    ENTRY_BG = "#252836"
    LOG_BG = "#0d1018"
    BTN_DIS = "#2a2d3e"

    root = tk.Tk()
    root.title("SEIA — Consulta de Processos")
    root.configure(bg=BG)
    root.geometry("760x800")
    root.minsize(680, 660)

    root.update_idletasks()
    root.geometry(
        f"760x800+{(root.winfo_screenwidth()-760)//2}+{(root.winfo_screenheight()-800)//2}"
    )

    def sep(parent):
        return tk.Frame(parent, bg=BORDA, height=1)

    # ───────────────── HEADER

    hdr = tk.Frame(root, bg=BG, pady=20)
    hdr.pack(fill="x", padx=28)

    tk.Label(
        hdr,
        text="SEIA",
        bg=BG,
        fg=ACENTO,
        font=("Segoe UI", 22, "bold")
    ).pack(side="left")

    tk.Label(
        hdr,
        text="  Consulta automática de processos",
        bg=BG,
        fg=SUBTEXTO,
        font=("Segoe UI", 11)
    ).pack(side="left", pady=4)

    sep(root).pack(fill="x", padx=28)

    # ───────────────── PAINEL

    painel = tk.Frame(root, bg=PAINEL, padx=22, pady=22)
    painel.pack(fill="x", padx=28, pady=(16, 0))

    tk.Label(
        painel,
        text="ARQUIVO CSV DE ENTRADA",
        bg=PAINEL,
        fg=SUBTEXTO,
        font=("Segoe UI", 8, "bold")
    ).pack(anchor="w")

    fr_csv = tk.Frame(painel, bg=PAINEL)
    fr_csv.pack(fill="x", pady=(12, 0))

    v_csv = tk.StringVar()

    ent_csv = tk.Entry(
        fr_csv,
        textvariable=v_csv,
        bg=ENTRY_BG,
        fg=TEXTO,
        insertbackground=TEXTO,
        relief="flat",
        bd=0,
        font=("Segoe UI", 10),
        highlightthickness=1,
        highlightbackground=BORDA,
        highlightcolor=ACENTO,
    )

    ent_csv.pack(side="left", fill="x", expand=True)

    def selecionar_csv():
        arq = filedialog.askopenfilename(
            title="Selecionar CSV",
            filetypes=[("CSV", "*.csv")]
        )

        if arq:
            v_csv.set(arq)

    tk.Button(
        fr_csv,
        text="Selecionar",
        command=selecionar_csv,
        bg=ACENTO,
        fg="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Segoe UI", 9, "bold"),
        padx=14,
        pady=7
    ).pack(side="left", padx=(10, 0))

    # ───────────────── LOGIN

    tk.Label(
        painel,
        text="ACESSO AO SEIA",
        bg=PAINEL,
        fg=SUBTEXTO,
        font=("Segoe UI", 8, "bold")
    ).pack(anchor="w", pady=(22, 6))

    fr_login = tk.Frame(painel, bg=PAINEL)
    fr_login.pack(fill="x")

    tk.Label(
        fr_login,
        text="Usuário",
        bg=PAINEL,
        fg=SUBTEXTO,
        font=("Segoe UI", 9)
    ).grid(row=0, column=0, sticky="w")

    tk.Label(
        fr_login,
        text="Senha",
        bg=PAINEL,
        fg=SUBTEXTO,
        font=("Segoe UI", 9)
    ).grid(row=0, column=1, sticky="w", padx=(14, 0))

    v_login = tk.StringVar()
    v_senha = tk.StringVar()

    ent_login = tk.Entry(
        fr_login,
        textvariable=v_login,
        bg=ENTRY_BG,
        fg=TEXTO,
        insertbackground=TEXTO,
        relief="flat",
        bd=0,
        font=("Segoe UI", 10),
        highlightthickness=1,
        highlightbackground=BORDA,
        highlightcolor=ACENTO,
        width=24
    )

    ent_login.grid(row=1, column=0, sticky="we", pady=(4, 0))

    ent_senha = tk.Entry(
        fr_login,
        textvariable=v_senha,
        show="•",
        bg=ENTRY_BG,
        fg=TEXTO,
        insertbackground=TEXTO,
        relief="flat",
        bd=0,
        font=("Segoe UI", 10),
        highlightthickness=1,
        highlightbackground=BORDA,
        highlightcolor=ACENTO,
        width=24
    )

    ent_senha.grid(row=1, column=1, sticky="we", padx=(14, 0), pady=(4, 0))

    # ───────────────── INSTRUÇÕES

    tk.Label(
        painel,
        text="INSTRUÇÕES DO CSV",
        bg=PAINEL,
        fg=SUBTEXTO,
        font=("Segoe UI", 8, "bold")
    ).pack(anchor="w", pady=(22, 6))

    instrucoes = (
        "O CSV deve conter obrigatoriamente uma coluna chamada:\n\n"
        "numero_processo\n\n"
        "Exemplo:\n"
        "2024.001.000123/INEMA/LIC-00123\n"
        "2024.001.000456/INEMA/LIC-00456\n\n"
        "• Salvar em CSV UTF-8\n"
        "• Não alterar o nome da coluna\n"
        "• Não deixar linhas vazias\n\n"
        "Dados extraídos por processo:\n"
        "  → Status · Nome do Empreendimento · E-mail"
    )

    tk.Label(
        painel,
        text=instrucoes,
        justify="left",
        anchor="w",
        bg=PAINEL,
        fg=TEXTO,
        font=("Segoe UI", 9),
    ).pack(fill="x")

    # ───────────────── SAÍDA

    sep(root).pack(fill="x", padx=28, pady=(14, 0))

    fr_saida = tk.Frame(root, bg=BG, pady=10)
    fr_saida.pack(fill="x", padx=28)

    tk.Label(
        fr_saida,
        text="Arquivo de saída:",
        bg=BG,
        fg=SUBTEXTO,
        font=("Segoe UI", 9)
    ).pack(side="left")

    saida_padrao = str(Path.cwd() / "resultado_processos.csv")

    v_saida = tk.StringVar(value=saida_padrao)

    tk.Entry(
        fr_saida,
        textvariable=v_saida,
        bg=ENTRY_BG,
        fg=SUBTEXTO,
        insertbackground=TEXTO,
        relief="flat",
        bd=0,
        font=("Segoe UI", 9),
        highlightthickness=1,
        highlightbackground=BORDA,
        highlightcolor=ACENTO,
        width=58
    ).pack(side="left", padx=(8, 0))

    # ───────────────── BOTÃO

    sep(root).pack(fill="x", padx=28)

    fr_btn = tk.Frame(root, bg=BG, pady=14)
    fr_btn.pack(fill="x", padx=28)

    v_status = tk.StringVar(value="Pronto para iniciar")

    lbl_status = tk.Label(
        fr_btn,
        textvariable=v_status,
        bg=BG,
        fg=SUBTEXTO,
        font=("Segoe UI", 9)
    )

    lbl_status.pack(side="left")

    # ───────────────── LOG

    sep(root).pack(fill="x", padx=28)

    fr_log = tk.Frame(root, bg=BG, pady=10)
    fr_log.pack(fill="both", expand=True, padx=28, pady=(0, 18))

    tk.Label(
        fr_log,
        text="LOG",
        bg=BG,
        fg=SUBTEXTO,
        font=("Segoe UI", 8, "bold")
    ).pack(anchor="w")

    txt = tk.Text(
        fr_log,
        bg=LOG_BG,
        fg="#9ca3bc",
        font=("Consolas", 9),
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=BORDA,
        wrap="word",
        state="disabled",
        pady=8,
        padx=10
    )

    txt.pack(fill="both", expand=True)

    txt.tag_config("ok", foreground=SUCESSO)
    txt.tag_config("erro", foreground=ERRO_C)
    txt.tag_config("info", foreground="#9ca3bc")
    txt.tag_config("prog", foreground=ACENTO)
    txt.tag_config("detalhe", foreground=SUBTEXTO)

    def add_log(msg):
        txt.config(state="normal")

        tag = (
            "erro" if ("✗" in msg or "Erro" in msg) else
            "ok"   if ("✓" in msg or "FINALIZADA" in msg) else
            "prog" if msg.startswith("[") else
            "detalhe" if msg.startswith("    ") else
            "info"
        )

        txt.insert("end", msg + "\n", tag)
        txt.see("end")
        txt.config(state="disabled")

    def iniciar():
        login = v_login.get().strip()
        senha = v_senha.get().strip()
        csv_entrada = v_csv.get().strip()
        csv_saida = v_saida.get().strip()

        if not login:
            messagebox.showerror("Erro", "Informe o usuário do SEIA.")
            return

        if not senha:
            messagebox.showerror("Erro", "Informe a senha do SEIA.")
            return

        if not csv_entrada:
            messagebox.showerror("Erro", "Selecione um arquivo CSV.")
            return

        if not Path(csv_entrada).exists():
            messagebox.showerror("Erro", "Arquivo CSV não encontrado.")
            return

        btn.config(state="disabled", bg=BTN_DIS)
        v_status.set("Executando consultas...")
        lbl_status.config(fg=ACENTO)

        txt.config(state="normal")
        txt.delete("1.0", "end")
        txt.config(state="disabled")

        def fim(ok):
            def _fim():
                btn.config(state="normal", bg=ACENTO)

                if ok:
                    v_status.set("Consulta finalizada")
                    lbl_status.config(fg=SUCESSO)
                else:
                    v_status.set("Execução encerrada com erro")
                    lbl_status.config(fg=ERRO_C)

            root.after(0, _fim)

        threading.Thread(
            target=executar_consulta,
            kwargs=dict(
                login=login,
                senha=senha,
                csv_entrada=csv_entrada,
                csv_saida=csv_saida,
                callback_log=lambda m: root.after(0, add_log, m),
                callback_fim=fim
            ),
            daemon=True
        ).start()

    btn = tk.Button(
        fr_btn,
        text="▶  Iniciar Consulta",
        command=iniciar,
        bg=ACENTO,
        fg="white",
        activebackground="#3a7ae8",
        activeforeground="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        padx=20,
        pady=9
    )

    btn.pack(side="right")

    root.mainloop()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    iniciar_interface()