import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from google.cloud import bigquery
from google.oauth2 import service_account

app = Flask(__name__)

app.secret_key = 'PALMEIRAS' 

USUARIO_ADMIN = "admin"
SENHA_ADMIN = "solar123"

CREDENTIALS_FILE = 'credentials.json'

def get_solar_data():
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            
            return {"total": 0, "defeitos": 0, "sem_defeito": 0}

        credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
        project_id = "deteccao-paineis-solares" # 
        client = bigquery.Client(credentials=credentials, project=project_id)

        query = """
            SELECT
                COUNT(DISTINCT panel_id) as total_paineis,
                COUNT(DISTINCT CASE WHEN status = 'Defeito' THEN panel_id END) as com_defeito
            FROM `deteccao-paineis-solares.solar_analysis.panels_segmented`
        """
        
        query_job = client.query(query)
        results = query_job.result()
        
        for row in results:
            total = row.total_paineis
            defeitos = row.com_defeito
            sem_defeito = total - defeitos
            #lembrar que tem q inverter os nomes dps pra ficar certo
            return {"total": total, "defeitos": defeitos, "sem_defeito": sem_defeito}
            
    except Exception as e:
        print(f"Erro: {e}")
        return {"total": 0, "defeitos": 0, "sem_defeito": 0}

# --- ROTAS ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Se já estiver logado, manda pro dashboard direto
    if 'usuario_logado' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        usuario = request.form.get('username')
        senha = request.form.get('password')

        if usuario == USUARIO_ADMIN and senha == SENHA_ADMIN:
            session['usuario_logado'] = usuario  
            return redirect(url_for('dashboard'))
        else:
            flash('Login ou senha incorretos!', 'error') 
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario_logado', None) 
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    
    if 'usuario_logado' not in session:
        return redirect(url_for('login'))
    
    data = get_solar_data()
    return render_template('dashboard.html', data=data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)