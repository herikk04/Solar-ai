import os
import json 
from flask import Flask, render_template, redirect, url_for, request, session, flash
from google.cloud import bigquery
from google.oauth2 import service_account

app = Flask(__name__)

# --- CONFIGURAÇÕES DE SEGURANÇA ---
# Secret Key é necessária para usar sessões (cookies seguros)
app.secret_key = 'PALMEIRAS' 

USUARIO_ADMIN = "admin"
SENHA_ADMIN = "solar123"

CREDENTIALS_FILE = 'credentials.json'

def get_solar_data():
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            return {"total": 0, "defeitos": 0, "sem_defeito": 0, "mapa": None}

        credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
        project_id = "deteccao-paineis-solares" 
        client = bigquery.Client(credentials=credentials, project=project_id)

        # 1. Totais (Mantém igual)
        query_totais = f"""
            SELECT
                COUNT(DISTINCT panel_id) as total_paineis,
                COUNT(DISTINCT CASE WHEN status = 'Defeito' THEN panel_id END) as com_defeito
            FROM `deteccao-paineis-solares.solar_analysis.panels_segmented_aula`
        """
        job_totais = client.query(query_totais)
        res_totais = list(job_totais.result())[0]
        
        # 2. Mapa - AQUI MUDOU: Adicionei 'panel_id' no SELECT
        query_mapa = f"""
            SELECT 
                panel_id, 
                ST_ASGEOJSON(panel_shape) as geometry, 
                status 
            FROM `deteccao-paineis-solares.solar_analysis.panels_segmented_aula`
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
                    "id": row.panel_id, # <--- Agora estamos enviando o ID real!
                    "status": row.status
                }
            })

        geojson_data = {
            "type": "FeatureCollection",
            "features": features
        }

        return {
            "total": res_totais.total_paineis, 
            "defeitos": res_totais.com_defeito, 
            "sem_defeito": res_totais.total_paineis - res_totais.com_defeito,
            "mapa": geojson_data
        }
            
    except Exception as e:
        print(f"Erro: {e}")
        return {"total": 0, "defeitos": 0, "sem_defeito": 0, "mapa": None}

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