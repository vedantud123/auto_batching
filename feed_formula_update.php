<?php
header('Content-Type: application/json');

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$mysqli = new mysqli($host, $user, $pass, $db);

if ($mysqli->connect_errno) {
    http_response_code(500);
    echo json_encode(['success' => false, 'message' => 'Failed to connect to database']);
    exit;
}

$mysqli->set_charset('utf8');

$input = json_decode(file_get_contents('php://input'), true);

if (!$input || !isset($input['client_id'], $input['data']) || !is_array($input['data'])) {
    http_response_code(400);
    echo json_encode(['success' => false, 'message' => 'Invalid input']);
    exit;
}

$clientId = intval($input['client_id']);  
$data = $input['data'];

$sql = "INSERT INTO feed_formula_detail
        (feed_formulaType, quantity, feed_rawMaterial_name, type, client_id)
        VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)";

$stmt = $mysqli->prepare($sql);
if (!$stmt) {
    http_response_code(500);
    echo json_encode(['success' => false, 'message' => 'Failed to prepare statement: '.$mysqli->error]);
    exit;
}

$mysqli->begin_transaction();

try {
    foreach ($data as $sheadObj) {
        foreach ($sheadObj as $sheadKey => $content) {

            if (isset($content['Feed_Formula']) && is_array($content['Feed_Formula'])) {
                foreach ($content['Feed_Formula'] as $material => $qty) {
                    $type = 'Feed_Formula';
                    $stmt->bind_param("sdssi", $sheadKey, $qty, $material, $type, $clientId); // ✅ qty as double
                    $stmt->execute();

                    if ($stmt->error) {
                        throw new Exception("Statement execute error: " . $stmt->error);
                    }
                }
            }

            if (isset($content['Feed_Medicine']) && is_array($content['Feed_Medicine'])) {
                foreach ($content['Feed_Medicine'] as $material => $qty) {
                    $type = 'Feed_Medicine';
                    $stmt->bind_param("sdssi", $sheadKey, $qty, $material, $type, $clientId); // ✅ qty as double
                    $stmt->execute();

                    if ($stmt->error) {
                        throw new Exception("Statement execute error: " . $stmt->error);
                    }
                }
            }
        }
    }

    $mysqli->commit();

    echo json_encode(['success' => true, 'message' => 'Feed formula updated successfully']);
} catch (Exception $e) {
    $mysqli->rollback();
    http_response_code(500);
    echo json_encode(['success' => false, 'message' => 'Database update failed', 'error' => $e->getMessage()]);
} finally {
    $stmt->close();
    $mysqli->close();
}
