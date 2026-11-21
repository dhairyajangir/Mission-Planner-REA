# Read type definitions directly from the portable EXE without executing its assemblies.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Reflection.Metadata
$archivePath = Join-Path $PSScriptRoot '../../mission-planner-portable.zip'
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
$buffer = [System.IO.MemoryStream]::new()
try {
    $member = $archive.GetEntry('MissionPlanner.exe').Open()
    try { $member.CopyTo($buffer) } finally { $member.Dispose() }
    $buffer.Position = 0
    $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($buffer)).ToLowerInvariant()
    $buffer.Position = 0
    $pe = [System.Reflection.PortableExecutable.PEReader]::new($buffer)
    $meta = [System.Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
    $types = [ordered]@{}
    foreach ($handle in $meta.TypeDefinitions) {
        $type = $meta.GetTypeDefinition($handle)
        $name = $meta.GetString($type.Namespace) + '.' + $meta.GetString($type.Name)
        if ($name -in @('MissionPlanner.Controls.PluginUI','MissionPlanner.Plugin.PluginLoader','MissionPlanner.Plugin.Plugin')) {
            $methods = foreach ($m in $type.GetMethods()) {
                $meta.GetString($meta.GetMethodDefinition($m).Name)
            }
            $types[$name] = @($methods)
        }
    }
    if ($types.Count -ne 3) { throw 'Missing expected release type' }
    $evidence = [ordered]@{
        member = 'MissionPlanner.exe'
        member_sha256 = $hash
        assembly = $meta.GetString($meta.GetAssemblyDefinition().Name)
        mvid = $meta.GetGuid($meta.GetModuleDefinition().Mvid).ToString()
        type_methods = $types
    }
    $evidence | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot 'release-types.json')
} finally {
    if ($pe) { $pe.Dispose() }
    $buffer.Dispose()
    $archive.Dispose()
}
