import requests
import duckdb
import pandas as pd

con = duckdb.connect('justice_observatory.db')
headers = {'Authorization': 'Token d29996b522a55b0bb980d58da2d90a056637a84b'}

#COURT--------------------------------------------------------------------------------------------------------------
url = "https://www.courtlistener.com/api/rest/v4/courts/"
all_courts = []
while url:
    response = requests.get(url, headers=headers)
    data = response.json()

    if 'results' in data:
        all_courts.extend(data['results'])
        print(f"Downloaded {len(all_courts)} record...")

        if len(all_courts) >= 100:
            break
        url_courts = data.get('next')
    else:
        break

# Transforming the list in a pandas dataframe
df_courts = pd.DataFrame(all_courts)
# creating table
con.execute("DROP TABLE IF EXISTS courts")
con.execute("CREATE TABLE IF NOT EXISTS courts AS SELECT * FROM df_courts")
print("Data courts imported on DuckDB!")
# First 7 rows
print("\n--- TABLE COURTS ---")
print(con.execute("SELECT id, full_name, jurisdiction FROM courts LIMIT 7").df())

#DOCKETS-----------------------------------------------------------------------------------------------------------------------#
#Importing dockets
url_dockets = "https://www.courtlistener.com/api/rest/v4/dockets/"
all_dockets = []

while url_dockets:
    response2 = requests.get(url_dockets, headers=headers)
    data_dockers = response2.json()
    if 'results' in data_dockers:
        all_dockets.extend(data_dockers['results'])
        if len(all_dockets) >= 100:
            break
        url_dockets = data_dockers.get('next')
    else:
        break
df_dockets = pd.DataFrame(all_dockets)
con.execute("DROP TABLE IF EXISTS dockets")
con.execute("CREATE TABLE IF NOT EXISTS dockets AS SELECT * FROM df_dockets")
print("Data dockets imported on DuckDB!")
print("\n --- TABLE DOCKETS ---")
print(con.execute("SELECT * FROM dockets LIMIT 7").df()) #60 variables

#ENTRIES------------------------------------------------------------------------------------------
url_entries = "https://www.courtlistener.com/api/rest/v4/clusters/"
all_entries = []
while url_entries:
    response3 = requests.get(url_entries, headers=headers)
    data_entries = response3.json()
    if 'results' in data_entries:
        all_entries.extend(data_entries['results'])
        if len(all_entries) >= 100:
            break
        url_entries = data_entries.get('next')
    else:
        break
df_entries = pd.DataFrame(all_entries)
con.execute("DROP TABLE IF EXISTS entries")
con.execute("CREATE TABLE IF NOT EXISTS entries AS SELECT * FROM df_entries")

#entries: this link requires more accessibility, so I used clusters instead
url_entries2 = "https://www.courtlistener.com/api/rest/v4/docket-entries/"
response4 = requests.get(url_entries2, headers=headers)
data_entries2 = response4.json()
if 'results' in data_entries2:
    en_list2 = data_entries2['results']
    df_entries2 = pd.DataFrame(en_list2)
    con.execute("DROP TABLE IF EXISTS entries2")
    con.execute("CREATE TABLE IF NOT EXISTS entries2 AS SELECT * FROM df_entries2")
    print("Data imported on DuckDB!")
#print("\n --- TABLE entries2 ---")
#print(con.execute("SELECT * FROM entries2 LIMIT 7").df())

#APPEALS----------------------------------------------------------------------------------------------------------------
url_appeals = "https://www.courtlistener.com/api/rest/v4/originating-court-information/"
all_appeals = []
while url_appeals:
    response4 = requests.get(url_appeals, headers=headers)
    data_app = response4.json()

    if 'results' in data_app:
        all_appeals.extend(data_app['results'])
        if len(all_appeals) >= 100:
            break
        url_appeals = data_app.get("next")
    else:
        break
df_app = pd.DataFrame(all_appeals)
con.execute("DROP TABLE IF EXISTS appeals")
con.execute("CREATE TABLE IF NOT EXISTS appeals AS SELECT * FROM df_app")
print("Data appeals imported on DuckDB!")
print("\n --- TABLE appeals ---")
print(con.execute("SELECT * FROM appeals LIMIT 7").df())

# Dockets Pandas DF
df_dockets = con.execute("SELECT * FROM dockets").df()
df_dockets.to_csv("dockets_export.csv", index=False)
# Courts
df_courts = con.execute("SELECT * FROM courts").df()
df_courts.to_csv("courts_export.csv", index=False)
# Entries
df_entries = con.execute("SELECT * FROM entries").df()
df_entries.to_csv("entries_export.csv", index=False)
#appeals
df_app = con.execute("SELECT * FROM appeals").df()
df_dockets.to_csv("appeals_export.csv", index=False)

print(df_courts.shape)
print(df_app.shape)
print(df_dockets.shape)
print(df_entries.shape)


