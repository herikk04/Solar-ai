import argparse
import logging
import json
import base64
import time
import io
from PIL import Image
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from apache_beam.pvalue import AsSingleton
from google.cloud import storage
from google.cloud import aiplatform

# --- CONFIGURAÇÕES (ATUALIZE AQUI) ---
PROJECT_ID = "deteccao-paineis-solares"           
REGION = "us-central1"
BUCKET_NAME = "solar-project-raw-data"       
ENDPOINT_ID = "943318304469024768"  # <--- ATENÇÃO: Coloque o ID do Endpoint ativo (P100)
TABLE_ID = f"{PROJECT_ID}:solar_analysis.panels_segmented_aula"

# --- FUNÇÕES AUXILIARES ---

def create_polygon_wkt(lat, lon):
    """
    Cria um quadrado WKT no sentido ANTI-HORÁRIO (Counter-Clockwise).
    Isso garante que o BigQuery entenda que é um quadrado preenchido, 
    e não o planeta inteiro.
    """
    offset = 0.000015 
    
    
    p1 = f"{lon - offset} {lat - offset}" # SW
    p2 = f"{lon + offset} {lat - offset}" # SE (Antes era o NW)
    p3 = f"{lon + offset} {lat + offset}" # NE
    p4 = f"{lon - offset} {lat + offset}" # NW
    
    return f"POLYGON(({p1}, {p2}, {p3}, {p4}, {p1}))"

class ReadJsonFromGCS(beam.DoFn):
    """Lê um arquivo JSON inteiro do GCS e retorna como dicionário/lista"""
    def process(self, file_path):
        from google.cloud import storage
        import json
        
        path_parts = file_path.replace("gs://", "").split("/", 1)
        bucket_name = path_parts[0]
        blob_name = path_parts[1]

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        content = blob.download_as_string()
        json_data = json.loads(content)
        yield json_data


class ExplodeMarkersByImage(beam.DoFn):
    """
    Versão "Modo Demo": Processa apenas um número limitado de imagens para apresentação.
    """
    def process(self, markers_json):
        # CONFIGURAÇÃO DE DEMONSTRAÇÃO
        # LIMIT_IMAGES = 100    

        images_seen = set()

        for panel_id, images_dict in markers_json.items():
            for image_name, coords in images_dict.items():
                
                base_name = image_name.replace(".norm_B", "")
                
                if not base_name.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff')):
                    base_name = f"{base_name}.JPG"
                
                clean_image_name_full_path = f"IMAGES/{base_name}"
                
                
                # CONTROLE DE LIMITE 
                if clean_image_name_full_path not in images_seen:
                    #if len(images_seen) >= LIMIT_IMAGES:
                    #    continue 
                    images_seen.add(clean_image_name_full_path)

                yield (clean_image_name_full_path, {
                    'panel_id': panel_id,
                    'x': coords['x'],
                    'y': coords['y']
                })
                

class ProcessImageAndPredict(beam.DoFn):
    def setup(self):
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(BUCKET_NAME)
        aiplatform.init(project=PROJECT_ID, location=REGION)
        self.endpoint = aiplatform.Endpoint(ENDPOINT_ID)

    def process(self, element, panels_metadata):
        image_filename, panels_to_crop = element
        
        logging.info(f"Processando imagem: {image_filename} contendo {len(panels_to_crop)} paineis.")

        try:
            blob = self.bucket.blob(image_filename)
            if not blob.exists():
                logging.warning(f"Imagem {image_filename} nao encontrada no bucket.")
                return

            image_bytes = blob.download_as_bytes()
            
            # --- REDIMENSIONAMENTO E COMPRESSÃO (Evita Erro 400) ---
            try:
                img = Image.open(io.BytesIO(image_bytes))
            except Exception as e:
                logging.error(f"Erro ao abrir imagem com PIL: {e}")
                return

            orig_w, orig_h = img.size
            max_size = 1024 # Reduzindo para 1024px
            ratio = min(max_size/orig_w, max_size/orig_h)
            new_size = (int(orig_w * ratio), int(orig_h * ratio))
            
            img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG", quality=80)
            compressed_image_bytes = buffer.getvalue()
            b64_image = base64.b64encode(compressed_image_bytes).decode('utf-8')

            # --- LOOP DE PREDIÇÃO ---
            for p in panels_to_crop:
                
                # Ajusta coordenadas para a nova escala
                orig_x = float(p['x'])
                orig_y = float(p['y'])
                scaled_x = int(orig_x * ratio)
                scaled_y = int(orig_y * ratio)

                instance = {
                    "image_b64": b64_image,
                    "point_x": scaled_x,
                    "point_y": scaled_y
                }

                # --- RETRY COM BACKOFF (Evita Erro 429) ---
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        response = self.endpoint.predict(instances=[instance])
                        
                        prediction = response.predictions[0]
                        panel_id = p['panel_id']
                        
                        # Busca metadados no Side Input
                        metadata = panels_metadata.get('panels', {}).get(panel_id, {})
                        
                        # Lógica de Classificação Simples
                        status = "Defeito" if prediction.get('found') else "Nao Encontrado"
                        confidence = prediction.get('confidence', 0.0)
                        
                        # Dados Geográficos
                        lat = float(metadata.get('latitude', 0.0))
                        lon = float(metadata.get('longitude', 0.0))
                        
                        # Cria o Polígono Visual para o Mapa
                        poly_wkt = create_polygon_wkt(lat, lon)

                        yield {
                            'panel_id': panel_id,
                            'source_image': image_filename,
                            'latitude': lat,
                            'longitude': lon,
                            'status': status,
                            'confidence': float(confidence),
                            'timestamp': "2025-11-24 12:00:00",
                            'panel_shape': poly_wkt # Campo novo Geográfico
                        }
                        break # Sucesso, sai do loop de retry

                    except Exception as e:
                        error_str = str(e)
                        # Se for cota ou indisponibilidade, espera e tenta de novo
                        if "429" in error_str or "503" in error_str:
                            wait_time = (2 ** attempt)
                            logging.warning(f"Erro Vertex (Cota). Esperando {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            logging.error(f"Erro fatal na predição: {e}")
                            break

        except Exception as e:
            logging.error(f"Falha grave na imagem {image_filename}: {e}")

def run():
    parser = argparse.ArgumentParser()
    known_args, pipeline_args = parser.parse_known_args()
    
    pipeline_options = PipelineOptions(pipeline_args)
    pipeline_options.view_as(SetupOptions).save_main_session = True
    pipeline_options.view_as(SetupOptions).setup_file = './setup.py'

    markers_path = f"gs://{BUCKET_NAME}/MARKERS.json"
    panels_path = f"gs://{BUCKET_NAME}/PANELS.json"

    with beam.Pipeline(options=pipeline_options) as p:
        
        # 1. Carrega Metadados (Side Input)
        panels_data = (
            p 
            | "Path Panels" >> beam.Create([panels_path])
            | "Ler PANELS.json" >> beam.ParDo(ReadJsonFromGCS())
        )

        # 2. Carrega e Organiza Imagens
        markers_data = (
            p 
            | "Path Markers" >> beam.Create([markers_path])
            | "Ler MARKERS.json" >> beam.ParDo(ReadJsonFromGCS())
            | "Organizar por Imagem" >> beam.ParDo(ExplodeMarkersByImage())
        )

        # 3. Agrupa tarefas
        grouped_images = (
            markers_data 
            | "Agrupar Paineis na Imagem" >> beam.GroupByKey()
        )

        # 4. Processa e Grava
        (
            grouped_images
            | "Processar e Predizer" >> beam.ParDo(
                ProcessImageAndPredict(), 
                panels_metadata=AsSingleton(panels_data)
            )
            | "Gravar no BigQuery" >> beam.io.WriteToBigQuery(
                TABLE_ID,
                # Schema atualizado com GEOGRAPHY
                schema="panel_id:STRING,source_image:STRING,latitude:FLOAT,longitude:FLOAT,status:STRING,confidence:FLOAT,timestamp:TIMESTAMP,panel_shape:GEOGRAPHY",
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
                create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED
            )
        )

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()