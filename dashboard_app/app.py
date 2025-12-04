import os
import json
from flask import Flask, render_template, redirect, url_for, request, session, flash
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv  # Import the library to read .env


app = Flask(__name__)

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_key_fallback')

USUARIO_ADMIN = os.getenv('ADMIN_USER')
SENHA_ADMIN = os.getenv('ADMIN_PASSWORD')
CREDENTIALS_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

def get_solar_data(tabela_alvo):
    try:
        # Check if the variable was loaded and if the file actually exists
        if not CREDENTIALS_FILE or not os.path.exists(CREDENTIALS_FILE):
            print("Erro: Arquivo de credenciais não encontrado ou variável de ambiente não definida.")
            return {"total": 0, "defeitos": 0, "sem_defeito": 0, "mapa": None}

        credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
        
        # Load Project and Dataset IDs from .env
        project_id = os.getenv('PROJECT_ID')
        dataset_id = os.getenv('DATASET_ID')

        # Safety check to ensure variables exist
        if not project_id or not dataset_id:
             print("Erro: PROJECT_ID ou DATASET_ID não definidos no .env")
             return {"total": 0, "defeitos": 0, "sem_defeito": 0, "mapa": None}
        
        client = bigquery.Client(credentials=credentials, project=project_id)

        # --- LOGIC TO SWITCH TABLES ---
        if tabela_alvo == 'aula':
            nome_tabela = "panels_segmented_aula"
            nome_exibicao = "VERSÃO AULA"
        else:
            nome_tabela = "panels_segmented_all"
            nome_exibicao = "PROJETO COMPLETO"

        # 1. Query Totals
        query_totais = f"""
            SELECT
                COUNT(DISTINCT panel_id) as total_paineis,
                COUNT(DISTINCT CASE WHEN status = 'Defeito' THEN panel_id END) as com_defeito
            FROM `{project_id}.{dataset_id}.{nome_tabela}`
        """
        job_totais = client.query(query_totais)
        res_totais = list(job_totais.result())[0]
        
        # 2. Query Map (GeoJSON)
        query_mapa = f"""
            SELECT 
                panel_id,
                ST_ASGEOJSON(panel_shape) as geometry, 
                status 
            FROM `{project_id}.{dataset_id}.{nome_tabela}`
            WHERE panel_shape IS NOT NULL
            LIMIT 1000 
        """
        
        job_mapa = client.query(query_mapa)
        
        features = []
        for row in job_mapa.result():
            geom = json.loads(row.geometry) 
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": { 
                    "id": row.panel_id,
                    "status": row.status 
                }
            })

        geojson_data = { "type": "FeatureCollection", "features": features }

        return {
            "total": res_totais.total_paineis, 
            "defeitos": res_totais.com_defeito, 
            "sem_defeito": res_totais.total_paineis - res_totais.com_defeito,
            "mapa": geojson_data,
            "nome_exibicao": nome_exibicao
        }
            
    except Exception as e:
        print(f"Erro ao buscar dados: {e}")
        return {"total": 0, "defeitos": 0, "sem_defeito": 0, "mapa": None}


# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_logado' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        usuario = request.form.get('username')
        senha = request.form.get('password')

        # Compare input against Environment Variables
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
    
    source = request.args.get('source', 'padrao')
    
    data = get_solar_data(source)
    
    return render_template('dashboard.html', data=data, current_source=source)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)