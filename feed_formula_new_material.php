<?php
header('Content-Type: application/json;charset=UTF-8');

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$mysqli = new mysqli($host, $user, $pass, $db);
if ($mysqli->connect_error) {
    http_response_code(500);
    echo json_encode(['success'=>false,'error'=>"DB connection failed"]);
    exit;
}

$input = json_decode(file_get_contents('php://input'), true);
$client_id = 1;
$material_name = trim($input['material']) ?? '';
$type = $input['type'] ?? '';

if (!$client_id || !$material_name || !$type) {
    http_response_code(400);
    echo json_encode(['success'=>false,'error'=>"Missing required data"]);
    exit;
}

$shead_json = @file_get_contents("http://localhost:8080/php/shead_chick_grower_json.php?client_id=$client_id");
if ($shead_json === false) {
    http_response_code(502);
    echo json_encode(['success'=>false,'error'=>"Unable to fetch SHEAD data"]);
    exit;
}
$shead_data = json_decode($shead_json, true);
if (!is_array($shead_data)) {
    http_response_code(502);
    echo json_encode(['success'=>false,'error'=>"Invalid JSON from SHEAD API"]);
    exit;
}

$inserted = 0;
foreach ($shead_data as $item) {
    if (!isset($item['shead_name'])) continue;
    $sheadNorm = strtolower(str_replace(' ', '_', $item['shead_name']));

    $chk = $mysqli->prepare("SELECT id FROM feed_formula_detail WHERE client_id=? AND feed_rawMaterial_name=? AND type=? AND feed_formulaType=?");
    $chk->bind_param("isss", $client_id, $material_name, $type, $sheadNorm);
    $chk->execute();
    $chk->store_result();
    if ($chk->num_rows === 0) {
        $ins = $mysqli->prepare("INSERT INTO feed_formula_detail 
            (client_id, feed_rawMaterial_name, type, feed_formulaType, quantity)
            VALUES(?,?,?,?,0)");
        $ins->bind_param("isss", $client_id, $material_name, $type, $sheadNorm);
        if ($ins->execute()) {
            $inserted++;
        } else {
            error_log("Insert error: " . $ins->error);
        }
        $ins->close();
    }
    $chk->close();
}

echo json_encode(['success'=>true,'message'=>"Success"]);
?> 
