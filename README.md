# BI_Group_20
Project Structure:
- BI_Dashboard: Power BI bpip and pdf
- BI_dataset: source dataset used by etl pipeline
- Báo cáo: final report document
- etl: ETL script for loading/trasnformation

Setup:
1. Clone this repository
2. Unzip the inventory_items.rar file in BI_dataset to change its into inventory_items.csv
3. Create a Python virtual environment
4. Install dependencies:
  pip install pandas numpy sqlalchemy pyodbc
5. Create database: BI_final
6. Change the DATA_PATH to where the BI_dataset is located
7. Run the following ETL pipelines to load the data in to the database:
  python etl/config.py
  python etl/etl_script.py
  python etl/update_region.py
8. Open BI_Dashboard/BI_Dashboard_final(new).pbit in Power BI
