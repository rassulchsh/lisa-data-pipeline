# LISA Slides Dataset Builder

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with your keys

# run mock server
uvicorn mock_server.app:app --reload --port 8000

# generate 100 drafts
python -m scripts.planner --count 100

# validate + metrics
python -m scripts.validate --indir dataset/dialogs/en/drafts
python -m scripts.metrics  --indir dataset/dialogs/en/drafts
