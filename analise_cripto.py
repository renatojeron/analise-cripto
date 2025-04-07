import time
import getpass
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Insira a senha para rodar o script
senha_correta = "senha123"
senha_digitada = getpass.getpass("Digite a senha para iniciar a análise: ")

if senha_digitada != senha_correta:
    print("❌ Senha incorreta. Encerrando o script.")
    exit()

print("🔓 Senha correta! Iniciando execuções automáticas a cada 10 minutos...\n")

# Importações restantes do seu script original:
import requests
import pandas as pd
import concurrent.futures
from jinja2 import Template
from tqdm import tqdm
from datetime import datetime

# [TODO: Insira aqui as funções find_opportunities(), select_best_opportunity(), generate_best_trade_html()]

# Função para envio de e-mail
def enviar_email_oportunidade(melhor):
    remetente = "renatojeron@gmail.com"
    senha_email = "xkif uvnb jvbs idhs"  # senha de app do Gmail
    destinatario = "renatojeron@gmail.com"

    assunto = f"🚀 Oportunidade: {melhor['symbol']} com Score {melhor['score']}!"
    corpo = f"""
✅ Nova oportunidade de swing trade encontrada!

📊 Moeda: {melhor['symbol']}
🔢 Score: {melhor['score']}
📈 Potencial de valorização: {melhor['potential']}%
💰 Preço atual: {melhor.get('price', 'N/A')}

📄 Acesse o relatório HTML para mais detalhes.

🕒 Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""

    mensagem = MIMEMultipart()
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.attach(MIMEText(corpo, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
            servidor.starttls()
            servidor.login(remetente, senha_email)
            servidor.send_message(mensagem)
        print(f"📧 E-mail enviado com sucesso para {destinatario}!")
    except Exception as e:
        print(f"⚠️ Erro ao enviar e-mail: {e}")

# Loop de análise automática
def executar_analise_repetidamente():
    while True:
        print(f"⏳ Análise iniciada: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        oportunidades = find_opportunities()
        melhor = select_best_opportunity(oportunidades)

        if melhor:
            generate_best_trade_html(melhor)
            print(f"✅ HTML gerado para {melhor['symbol']} com potencial de {melhor['potential']}%!")

            if melhor["score"] > 4:
                enviar_email_oportunidade(melhor)
        else:
            print("⚠️ Nenhuma oportunidade encontrada no momento.")

        print("🕒 Aguardando 10 minutos para próxima execução...\n")
        time.sleep(600)

# Iniciar execução em loop
executar_analise_repetidamente()
