import zipfile
import xml.etree.ElementTree as ET

def verify():
    with zipfile.ZipFile('Plataforma.pptx', 'r') as z:
        with open('slides_updated_runs.txt', 'w', encoding='utf-8') as out:
            for i in range(1, 11):
                name = f'ppt/slides/slide{i}.xml'
                root = ET.fromstring(z.read(name))
                out.write(f'*** SLIDE {i} ***\n')
                for sp in root.iter('{http://schemas.openxmlformats.org/presentationml/2006/main}sp'):
                    cNvPr = sp.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr')
                    sp_name = cNvPr.get('name') if cNvPr is not None else 'unknown'
                    txBody = sp.find('{http://schemas.openxmlformats.org/presentationml/2006/main}txBody')
                    if txBody is not None:
                        for p_idx, p in enumerate(txBody.findall('{http://schemas.openxmlformats.org/drawingml/2006/main}p')):
                            runs = [r.find('{http://schemas.openxmlformats.org/drawingml/2006/main}t').text
                                    for r in p.findall('{http://schemas.openxmlformats.org/drawingml/2006/main}r')
                                    if r.find('{http://schemas.openxmlformats.org/drawingml/2006/main}t') is not None]
                            if runs:
                                out.write(f'  [{sp_name} p{p_idx}]: "{" ".join(runs)}"\n')

        # Check placeholder terms across all XML files in the ZIP
        placeholders = ['Warner', 'Spencer', 'Universidad', 'Técnica', 'RabbitMQ', 'Kafka', 'Kubernetes', 'POST /recursos']
        found = []
        for item in z.namelist():
            if item.endswith('.xml'):
                content = z.read(item).decode('utf-8', errors='ignore')
                for ph in placeholders:
                    if ph.lower() in content.lower():
                        found.append((item, ph))
        
        if found:
            print("ADVERTENCIA: Se encontraron placeholders restantes:")
            for item, ph in found:
                print(f"  En {item}: {ph}")
        else:
            print("¡ÉXITO TOTAL! No queda ningún placeholder en la presentación.")

if __name__ == '__main__':
    verify()
