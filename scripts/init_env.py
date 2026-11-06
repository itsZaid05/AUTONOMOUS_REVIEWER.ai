"""Create development credentials once, preserving existing .env files."""
import secrets
from pathlib import Path
p=Path('.env')
if p.exists():print('.env already exists; preserved')
else:
    password=secrets.token_hex(24)
    template=Path('.env.example').read_text().replace('POSTGRES_PASSWORD=CHANGE_ME','POSTGRES_PASSWORD='+password).replace('paperflow:CHANGE_ME@','paperflow:'+password+'@').replace('ADMIN_TOKEN=CHANGE_ME','ADMIN_TOKEN='+secrets.token_hex(32)).replace('SIGNING_KEY=CHANGE_ME','SIGNING_KEY='+secrets.token_hex(32))
    p.write_text(template);p.chmod(0o600);print('Created .env with random local credentials; values withheld')
