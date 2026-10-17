import os

with open('app/templates/manager_overview.html', 'r', encoding='utf-8') as f:
    ov_lines = f.readlines()

# Extract the full manager dashboard content from manager_overview
# We want from `<div class="d-flex justify-content-between` to `<hr class="mb-5">` (inclusive)
start_idx = -1
end_idx = -1
for i, line in enumerate(ov_lines):
    if '<div class="d-flex justify-content-between' in line:
        start_idx = i
    if '<!-- CÁC BẢNG QUẢN LÝ CHI TIẾT' in line:
        end_idx = i - 1
        break

if start_idx == -1 or end_idx == -1:
    print("Cannot find markers in manager_overview.html")
    exit(1)

manager_dashboard = ov_lines[start_idx:end_idx]

with open('app/templates/index.html', 'r', encoding='utf-8') as f:
    idx_lines = f.readlines()

start_index = -1
end_index = -1

for i, line in enumerate(idx_lines):
    if "<!-- Khu vực của Quản lý -->" in line:
        start_index = i + 1
        
    # Find the final endif that closes the user.role if-else block
    if start_index != -1 and i > start_index and "{% endif %}" in line and "</div>" in idx_lines[i+1]:
        end_index = i
        break

if start_index == -1 or end_index == -1:
    print("Cannot find markers in index.html")
    exit(1)

new_idx_lines = idx_lines[:start_index] + manager_dashboard + idx_lines[end_index:]

with open('app/templates/index.html', 'w', encoding='utf-8') as f:
    f.writelines(new_idx_lines)

print("Fixed index.html")
