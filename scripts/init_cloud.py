"""Initialize native cloud development without replacing existing credentials."""
from pathlib import Path
import secrets
root=Path(__file__).resolve().parents[1]
p=root/'.env'
if p.exists():print('Existing .env preserved')
else:
 password=secrets.token_hex(32)
 p.write_text('DATABASE_URL=postgresql+psycopg://paperflow:'+password+'@127.0.0.1:5432/paperflow\nPOSTGRES_PASSWORD='+password+'\nADMIN_TOKEN='+secrets.token_hex(32)+'\nSIGNING_KEY='+secrets.token_hex(32)+'\n')
 p.chmod(0o600);print('Cloud configuration created; credential values withheld')
