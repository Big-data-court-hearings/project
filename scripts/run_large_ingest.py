# Runner for large-scale ingestion test (50k)
import sys
sys.path.append(r'C:/code/courtlistener-project')
import ingestion.config as cfg
cfg.MAX_RECORDS = 50000
print('Starting large ingestion run with MAX_RECORDS=', cfg.MAX_RECORDS)
import ingestion.ingest_dockets
print('Large ingestion runner completed')
