# Detecção de Falhas e Segmentação de Painéis Solares com IA e Big Data

Este repositório contém uma solução completa (End-to-End) de **Engenharia de Dados e MLOps** para inspeção automática de fazendas solares. O sistema processa imagens térmicas capturadas por drones, utiliza Inteligência Artificial para segmentar e identificar defeitos, e apresenta os resultados em um Dashboard Geográfico.

## Arquitetura da Solução

O fluxo de dados segue uma arquitetura moderna na **Google Cloud Platform (GCP)**:

1.  **Ingestão (Data Lake):** Imagens brutas e metadados (`JSON`) são armazenados no **Google Cloud Storage**.
2.  **Processamento (ETL):** Um pipeline **Google Cloud Dataflow (Apache Beam)** lê os arquivos, organiza as tarefas e pré-processa as imagens.
3.  **Inteligência Artificial (Inference):** O Dataflow envia as imagens para um Endpoint no **Vertex AI**, onde um modelo **YOLOv8** customizado segmenta o painel e classifica falhas (Hotspots).
4.  **Armazenamento (Data Warehouse):** Os resultados (status do defeito + polígono geográfico) são gravados no **Google BigQuery**.
5.  **Apresentação (Gold Layer):** Uma aplicação Web (**Flask**) consulta o BigQuery e renderiza os mapas de calor e estatísticas em tempo real.

---

## Estrutura do Repositório

O projeto está dividido em três módulos principais:

```text
/
├── pipeline_etl/           # O Motor de Processamento (Dataflow)
│   ├── main_pipeline.py    # Script de orquestração Apache Beam
│   └── setup.py            # Dependências dos workers do Dataflow
│
├── model_serving/          # A Inteligência Artificial (Vertex AI)
│   ├── Dockerfile          # Receita da imagem do container
│   ├── app.py              # API Flask para servir o modelo YOLO
│   └── requirements.txt    # Bibliotecas de ML (Torch, Ultralytics)
│
└── dashboard_app/          # A Visualização (Gold Layer)
    ├── app.py              # Backend Flask que conecta no BigQuery
    ├── credentials.json    # (Não comitado) Credenciais de Serviço GCP
    ├── static/
    │   └── style.css       # Estilo Futurista/Dark Mode
    └── templates/
        └── index.html      # Frontend com mapas e gráficos