# Detecção de Falhas e Segmentação de Painéis Solares com IA e Big Data

Pipeline de MLOps end-to-end para inspeção automática de fazendas solares: processa imagens térmicas capturadas por drone, usa visão computacional para segmentar painéis e identificar falhas (hotspots), e apresenta os resultados em um dashboard geográfico em tempo real.

---

## Sobre o projeto

Inspeção manual de painéis solares em larga escala é lenta e cara: um técnico precisa revisar imagem por imagem em busca de hotspots (pontos de superaquecimento que indicam falha). Esse projeto automatiza essa etapa, transformando imagens térmicas brutas em um mapa de calor consultável, com status de cada painel da fazenda.

A solução foi desenhada como um pipeline de dados real, não um notebook isolado: ingestão, processamento distribuído, inferência de modelo servido em produção e camada de apresentação — cada uma como um componente independente.

<!-- TODO: adicionar 1-2 screenshots ou GIF do dashboard aqui. É a parte mais visual do projeto e vai vender bem mais do que texto. -->

---

## Arquitetura da solução

O fluxo de dados segue uma arquitetura na **Google Cloud Platform (GCP)**:

```
Drone (imagens térmicas)
        │
        ▼
┌───────────────────────┐
│  Cloud Storage         │  Data Lake: imagens brutas + metadados (JSON)
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Dataflow (Apache Beam)│  ETL: organiza tarefas, pré-processa imagens
│  pipeline_etl/         │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Vertex AI             │  Inferência: modelo YOLOv8 customizado
│  model_serving/        │  segmenta painel + classifica falhas (hotspots)
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  BigQuery               │  Data Warehouse: status do defeito + polígono geográfico
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Dashboard (Flask)      │  Gold Layer: mapas de calor e estatísticas em tempo real
│  dashboard_app/        │
└───────────────────────┘
```

1. **Ingestão (Data Lake)** — imagens brutas e metadados são armazenados no Google Cloud Storage.
2. **Processamento (ETL)** — um pipeline Dataflow (Apache Beam) lê os arquivos, organiza as tarefas e pré-processa as imagens.
3. **Inteligência Artificial (Inference)** — o Dataflow envia as imagens para um endpoint no Vertex AI, onde um modelo YOLOv8 customizado segmenta o painel e classifica falhas.
4. **Armazenamento (Data Warehouse)** — os resultados (status do defeito + polígono geográfico) são gravados no BigQuery.
5. **Apresentação (Gold Layer)** — uma aplicação Flask consulta o BigQuery e renderiza mapas de calor e estatísticas em tempo real.

---

## Stack técnico

| Camada              | Tecnologia                          |
| -------------------- | ------------------------------------ |
| Data Lake            | Google Cloud Storage                 |
| Processamento (ETL)  | Apache Beam (Google Cloud Dataflow)  |
| Modelo de visão      | YOLOv8 (Ultralytics) + PyTorch       |
| Serving do modelo    | Vertex AI, Flask, Docker             |
| Data Warehouse       | BigQuery                             |
| Dashboard            | Flask, HTML/CSS                      |

---

## Estrutura do repositório

O projeto está dividido em três módulos principais:

```
/
├── pipeline_etl/           # Motor de processamento (Dataflow)
│   ├── main_pipeline.py    # Script de orquestração Apache Beam
│   └── setup.py            # Dependências dos workers do Dataflow
│
├── model_serving/          # Inteligência artificial (Vertex AI)
│   ├── Dockerfile          # Imagem do container
│   ├── app.py              # API Flask que serve o modelo YOLO
│   └── requirements.txt    # Bibliotecas de ML (Torch, Ultralytics)
│
└── dashboard_app/          # Visualização (Gold Layer)
    ├── app.py              # Backend Flask que consulta o BigQuery
    ├── credentials.json    # (não comitado) Credenciais de serviço GCP
    ├── static/
    │   └── style.css       # Estilo dark mode
    └── templates/
        └── index.html      # Frontend com mapas e gráficos
```

---

## Status do projeto

Este projeto foi desenvolvido como trabalho final de uma disciplina do curso de Inteligência Artificial na UFG. O pipeline esteve provisionado e em execução na GCP durante o período do trabalho — ingestão, processamento via Dataflow, inferência no Vertex AI e dashboard consultando o BigQuery funcionaram de ponta a ponta. Os recursos de cloud não estão mais ativos hoje (não há custo de infraestrutura sendo mantido fora do período do curso), mas o código e a arquitetura aqui refletem uma implementação que rodou de fato, não um protótipo teórico.

Como este projeto depende de recursos provisionados na GCP (bucket no Cloud Storage, job no Dataflow, endpoint no Vertex AI, dataset no BigQuery), não há um único comando de "rodar localmente" — cada módulo é implantado separadamente:

- `model_serving/` — build e deploy da imagem Docker como endpoint do Vertex AI.
- `pipeline_etl/` — submissão do job ao Dataflow (`python main_pipeline.py --runner DataflowRunner ...`).
- `dashboard_app/` — pode ser executado localmente com `python app.py`, desde que `credentials.json` esteja configurado com acesso ao BigQuery.

<!-- TODO: se quiser, eu detalho os comandos exatos de cada etapa — me passa os parâmetros reais (nome do projeto GCP, bucket, dataset) ou só a estrutura de variáveis de ambiente que cada módulo espera. -->

---

## Licença

<!-- TODO: adicionar licença, se aplicável (ex: MIT) -->
