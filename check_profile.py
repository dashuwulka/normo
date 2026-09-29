import json
from pathlib import Path

from app.models.profile import Profile


profile_path = Path("profiles/gost_r_7_0_110_2025.json")

with profile_path.open("r", encoding="utf-8") as file:
    raw_data = json.load(file)

profile = Profile.model_validate(raw_data)

print(f"Профиль загружен: {profile.name}")
print(f"Количество правил: {len(profile.rules)}")

for rule in profile.rules:
    print(f"- {rule.id}: {rule.description}")