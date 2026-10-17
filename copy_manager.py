import sys

with open('app/templates/manager_overview.html', 'r', encoding='utf-8') as f:
    overview_lines = f.readlines()

# Extract lines 6 to 245 (0-indexed 5 to 245)
# Actually let's just find the start and end by markers
start_idx = -1
end_idx = -1
for i, line in enumerate(overview_lines):
    if "<!-- 1. KPI Đầu trang -->" in line:
        start_idx = i - 16 # Adjust to get the filter header too
    if "<!-- CÁC BẢNG QUẢN LÝ CHI TIẾT (CŨ) DƯỚI ĐÂY -->" in line:
        end_idx = i - 2 # Exclude the <hr>

if start_idx == -1 or end_idx == -1:
    print("Could not find markers in manager_overview.html")
    sys.exit(1)

manager_dashboard_html = "".join(overview_lines[start_idx:end_idx])


with open('app/templates/index.html', 'r', encoding='utf-8') as f:
    index_lines = f.readlines()

start_index = -1
end_index = -1

for i, line in enumerate(index_lines):
    if "<!-- Khu vực của Quản lý -->" in line:
        start_index = i + 1
    if start_index != -1 and i > start_index and "{% endif %}" in line:
        end_index = i
        break

if start_index == -1 or end_index == -1:
    print("Could not find manager section in index.html")
    sys.exit(1)

new_index_lines = index_lines[:start_index] + [manager_dashboard_html + "\n"] + index_lines[end_index:]

with open('app/templates/index.html', 'w', encoding='utf-8') as f:
    f.writelines(new_index_lines)

print("Successfully moved manager dashboard to index.html")
