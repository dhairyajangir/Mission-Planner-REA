"""Inventory a pinned MAVProxy checkout against its tracked Git blobs."""
import hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent.parent;repo=root/'ardupilot-mavproxy-source'
commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
assert commit=='8258c223d8da58f2db71a1c2eabb6834f35e8d8c'
raw=subprocess.check_output(['git','-C',str(repo),'ls-files','-s','-z'])
def blob(data):return hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest()
rows=[]
for item in raw.split(b'\0'):
    if not item:continue
    meta,path=item.split(b'\t',1);mode,digest,stage=meta.decode().split();name=path.decode('utf8')
    if stage!='0':raise RuntimeError('unmerged '+name)
    p=repo/name
    if mode!='100644' and mode!='100755':
        rows.append({'path':name,'mode':mode,'git_blob':digest,'status':'not_checked_special_mode'});continue
    if not p.is_file():
        rows.append({'path':name,'mode':mode,'git_blob':digest,'status':'missing'});continue
    data=p.read_bytes();exact=blob(data)==digest;normalized=blob(data.replace(b'\r\n',b'\n'))==digest
    rows.append({'path':name,'mode':mode,'git_blob':digest,'status':'exact' if exact else 'crlf_normalized' if normalized else 'mismatch','size':len(data)})
counts={status:sum(r['status']==status for r in rows) for status in ('exact','crlf_normalized','mismatch','missing','not_checked_special_mode')}
summary={'commit':commit,'repository':'https://github.com/ArduPilot/MAVProxy','tracked':len(rows),'counts':counts,'files':rows}
out=root/'mission-planner-binary-evidence/mavproxy-source-inventory.json';out.write_text(json.dumps(summary,indent=2)+'\n')
print(counts,'tracked',len(rows))
