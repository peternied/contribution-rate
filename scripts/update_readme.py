import os
import sys
from datetime import datetime

timestamp = sys.argv[1]
update_date = datetime.strptime(timestamp, '%Y%m%d').strftime('Updated on %B %d, %Y')
reports_path = f'reports/{timestamp}'
readme_path = 'README.md'

if not os.path.exists(reports_path):
    print(f"Reports path {reports_path} does not exist.")
    sys.exit(1)

readme_content = []
if os.path.exists(readme_path):
    with open(readme_path, 'r') as file:
        readme_content = file.readlines()

# Look for start and end markers or append if not found
start_marker = '<!-- REPORTS_START -->\n'
end_marker = '<!-- REPORTS_END -->\n'
if start_marker in readme_content:
    start_index = readme_content.index(start_marker)
    end_index = readme_content.index(end_marker, start_index) if end_marker in readme_content else start_index + 1
    readme_content = readme_content[:start_index+1] + readme_content[end_index:]
else:
    readme_content += [start_marker, end_marker]

# Insert new report links
update_date_index = readme_content.index(start_marker) + 1
readme_content.insert(update_date_index, f"_{update_date}_\n")
new_links_index = update_date_index + 1
report_files = os.listdir(reports_path)
for report_file in sorted(report_files):
    link = f"- [Latest {report_file.split('.')[0]} Report](/reports/{timestamp}/{report_file})\n"
    readme_content.insert(new_links_index, link)
    new_links_index += 1

# Write back to README
with open(readme_path, 'w') as file:
    file.writelines(readme_content)
