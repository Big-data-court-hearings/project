import pandas as pd
import os
from pathlib import Path

# for robust path access
base_path = Path(__file__).parent 
output_path = base_path / ".." / "data" / "raw_json" / 'dockets_terminated_2024_onwards.jsonl'

input_path = base_path / ".." /'dockets-2026-03-31.csv'

chunk_size = 50000 

if os.path.exists(output_path):
    os.remove(output_path)


try:
    total_processed = 0
    for chunk in pd.read_csv(input_path, 
                            chunksize=chunk_size, 
                            on_bad_lines='skip', 
                            dtype=str, 
                            low_memory=False):
        
        # Conversione data
        chunk['date_terminated'] = pd.to_datetime(chunk['date_terminated'], errors='coerce')
        
        # Filtro: solo fino al 2021
        mask = (chunk['date_terminated'].notna()) & (chunk['date_terminated'].dt.year >= 2024)
        filtered_chunk = chunk[mask].copy()
        
        if not filtered_chunk.empty:
            filtered_chunk['date_terminated'] = filtered_chunk['date_terminated'].dt.strftime('%Y-%m-%d')
            filtered_chunk.to_json(output_path, 
                                   orient='records', 
                                   lines=True, 
                                   mode='a')
        total_processed += len(filtered_chunk)
        
        print(f"Processed {total_processed} rows...")
        del chunk

    print(f"Done! File available at: {output_path}")

except Exception as e:
    print(f"Error: {e}")