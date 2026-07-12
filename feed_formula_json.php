<?php
header('Content-Type: application/json');

$response = [];

$mysqli = new mysqli("localhost", "root", "sunfra", "auto_batching");
if ($mysqli->connect_error) {
    echo json_encode(['error' => "Connection failed: " . $mysqli->connect_error]);
    exit;
}

$client_id = 1;
if (!$client_id) {
    echo json_encode(["status" => "error", "message" => "❌ Client ID missing from request"]);
    exit;
}

$stmt_check_material = $mysqli->prepare("SELECT name FROM feed_rawmaterial WHERE client_id = ? LIMIT 1");
$stmt_check_material->bind_param("i", $client_id);
$stmt_check_material->execute();
$stmt_check_material->store_result();

if ($stmt_check_material->num_rows > 0) {
    $stmt_check_material->bind_result($material_name);
    $stmt_check_material->fetch();
} else {
    $stmt_check_material->close();
    goto SKIP_INSERT; 
}
$stmt_check_material->close();

$stmt_check_formula = $mysqli->prepare("SELECT id FROM feed_formula_detail WHERE client_id = ? LIMIT 1");
$stmt_check_formula->bind_param("i", $client_id);
$stmt_check_formula->execute();
$stmt_check_formula->store_result();

if ($stmt_check_formula->num_rows === 0) {
    $shead_url = "http://localhost:8080/php/shead_chick_grower_json.php?client_id=$client_id";
    $shead_response = file_get_contents($shead_url);

    if ($shead_response !== false) {
        $shead_data = json_decode($shead_response, true);
        if (is_array($shead_data)) {
            $shead_count = 1;
            foreach ($shead_data as $item) {
                if (isset($item['shead_name'])) {
                    $shead_column = "shead_" . $shead_count++;
                    $stmt_insert = $mysqli->prepare("
                        INSERT INTO feed_formula_detail 
                        (feed_formulaType, quantity, feed_rawMaterial_name, type, client_id)
                        VALUES (?, 0, ?, 'Feed_Formula', ?)
                    ");
                    $stmt_insert->bind_param("ssi", $shead_column, $material_name, $client_id);
                    $stmt_insert->execute();
                    $stmt_insert->close();
                }
            }
        }
    }
}
$stmt_check_formula->close();

SKIP_INSERT:

/* ------------------------------------------------
   Step 3: Fetch shead data
-------------------------------------------------- */
$shead_url = "http://localhost:8080/php/shead_chick_grower_json.php?client_id=$client_id";
$shead_response = file_get_contents($shead_url);

if ($shead_response === false) {
    echo json_encode(["error" => "Unable to fetch shead data"]);
    exit;
}

$shead_data = json_decode($shead_response, true);
if (!is_array($shead_data)) {
    echo json_encode(["error" => "Invalid JSON received"]);
    exit;
}

$shead_list = [];
foreach ($shead_data as $item) {
    if (isset($item['shead_name'])) {
        $normalized = strtolower(str_replace(' ', '_', $item['shead_name']));
        $shead_list[] = $normalized;
    }
}

if (empty($shead_list)) {
    echo json_encode(["error" => "No shead data found for client"]);
    exit;
}

/* ------------------------------------------------
   Step 4: Build query dynamically
-------------------------------------------------- */
$sum_fields = '';
foreach ($shead_list as $shead_name) {
    $sum_fields .= "SUM(CASE WHEN feed_formulaType = '$shead_name' THEN quantity ELSE 0 END) AS `$shead_name`,\n    ";
}
$sum_fields = rtrim($sum_fields, ",\n    ");

$query = "
    SELECT
        type,
        feed_rawMaterial_name AS Material,
        $sum_fields
    FROM feed_formula_detail
    WHERE client_id = ?
    GROUP BY type, feed_rawMaterial_name
    ORDER BY FIELD(type, 'Feed_Formula', 'Feed_Medicine')
";

$structuredData = [];

/* ------------------------------------------------
   Step 5: Run query with prepared statement
-------------------------------------------------- */
$stmt = $mysqli->prepare($query);
$stmt->bind_param("i", $client_id);
$stmt->execute();
$result = $stmt->get_result();

if ($result) {
    while ($row = $result->fetch_assoc()) {
        $type = $row['type']; 
        $material = $row['Material'];

        foreach ($shead_list as $shead) {
            $quantity = (float)($row[$shead] ?? 0);
            $rounded = round($quantity, 2);
            $finalQty = (fmod($rounded, 1) === 0.0) ? (int)$rounded : $rounded;

            if (!isset($structuredData[$shead])) {
                $structuredData[$shead] = [];
            }

            if (!isset($structuredData[$shead][$type])) {
                $structuredData[$shead][$type] = [];
            }
            $structuredData[$shead][$type][$material] = $finalQty;
        }
    }

    $formatted = [];
    foreach ($structuredData as $shead => $typeData) {
        $formatted[] = [
            $shead => $typeData
        ];
    }

    $response[(string)$client_id] = $formatted;
    $result->free();
} else {
    $response[(string)$client_id] = [];
    $response['error'] = "No data found";
}

$stmt->close();
$mysqli->close();

echo json_encode($response, JSON_PRETTY_PRINT);
?>
