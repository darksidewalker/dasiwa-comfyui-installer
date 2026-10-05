package uistatic

import (
	"os"
	"os/exec"
	"testing"
)

func TestHardwareOptionsGateCUDAExtensions(t *testing.T) {
	node, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node is required for the embedded UI behavior test")
	}
	source, err := os.ReadFile("static/app.js")
	if err != nil {
		t.Fatal(err)
	}
	const script = `
const assert = require('node:assert/strict');
const source = process.argv[1];
const start = source.indexOf('function syncHardwareOptions()');
assert.ok(start >= 0, 'missing vendor-gating function');
const end = source.indexOf('\nfunction refreshReview()', start);
const fields = new Map();
function field(selector) {
 if (!fields.has(selector)) fields.set(selector, {value:'',checked:true,disabled:false,textContent:''});
 return fields.get(selector);
}
const document = {querySelector:field};
const selectedMode = ()=>'fresh';
const selectedDownloadChoices = ()=>[];
const buildConfigOverrides = ()=>({});
const build = new Function('document','selectedMode','selectedDownloadChoices','buildConfigOverrides',source.slice(start,end)+'; return {syncHardwareOptions, buildPlan};')(document,selectedMode,selectedDownloadChoices,buildConfigOverrides);
for (const vendor of ['AMD','INTEL']) {
 field('#vendor').value=vendor;
 for (const id of ['want_sage','want_radial','want_flash']) field('#'+id).checked=true;
 const plan=build.buildPlan();
 for (const id of ['want_sage','want_radial','want_flash']) {
  assert.equal(field('#'+id).disabled,true);
  assert.equal(field('#'+id).checked,false);
  assert.equal(plan[id],false);
 }
 assert.equal(field('#cuda_target').disabled,true);
}
field('#vendor').value='NVIDIA';
build.syncHardwareOptions();
for (const id of ['want_sage','want_radial','want_flash']) {
 assert.equal(field('#'+id).disabled,false);
 assert.equal(field('#'+id).checked,false, 'switching back must not opt in automatically');
}
assert.equal(field('#cuda_target').disabled,false);
console.log('AMD/Intel/NVIDIA vendor gates and submitted plan verified');
`
	if out, err := exec.Command(node, "-e", script, string(source)).CombinedOutput(); err != nil {
		t.Fatalf("UI hardware test: %v\n%s", err, out)
	}
}
