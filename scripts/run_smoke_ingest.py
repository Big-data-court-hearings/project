# Runner for smoke ingestion
import sys
sys.path.append(r'C:/code/courtlistener-project')
import ingestion.config as cfg
cfg.MAX_RECORDS = 100
import ingestion.ingest_dockets
print('Smoke ingestion runner completed')
