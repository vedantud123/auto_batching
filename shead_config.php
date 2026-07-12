<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$client_id = 1;

$current_sheads  = $conn->query("SELECT COUNT(*) as cnt FROM shead_config WHERE shead_name LIKE 'Shead%'")->fetch_assoc()['cnt'];
$current_chicks  = $conn->query("SELECT COUNT(*) as cnt FROM shead_config WHERE shead_name LIKE 'Chick%'")->fetch_assoc()['cnt'];
$current_growers = $conn->query("SELECT COUNT(*) as cnt FROM shead_config WHERE shead_name LIKE 'Grower%'")->fetch_assoc()['cnt'];

$message = "";

$mac_address = trim(shell_exec("cat /sys/class/net/wlan0/address"));
$mac_address_formatted = str_replace(":", "-", $mac_address);

$apiUrl = "https://sunfra.com/farm/csv/feed_raw_material_json.php?mac_address=" . $mac_address_formatted;
$response = @file_get_contents($apiUrl);
$raw_materials = [];
if ($response !== FALSE) {
    $data = json_decode($response, true);
    if (isset($data['material'])) {
        foreach ($data['material'] as $mat) {
            if (isset($mat['type']) && strtolower($mat['type']) === 'raw material') {
                $raw_materials[] = $mat['name'];
            }
        }
    }
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['shead_count'])) {
    $shead_count  = (int)$_POST['shead_count'];
    $chick_count  = (int)$_POST['chick_count'];
    $grower_count = (int)$_POST['grower_count'];

    $conn->query("DELETE FROM shead_config WHERE client_id = $client_id");

    $stmt = $conn->prepare("INSERT INTO shead_config (shead_name, description, client_id) VALUES (?, ?, ?)");

    for ($i = 1; $i <= $shead_count; $i++) {
        $name = "Shead $i";
        $desc = "Shead Number: $i";
        $stmt->bind_param("ssi", $name, $desc, $client_id);
        $stmt->execute();
    }
    for ($i = 1; $i <= $chick_count; $i++) {
        $name = "Chick $i";
        $desc = "Chick Number: $i";
        $stmt->bind_param("ssi", $name, $desc, $client_id);
        $stmt->execute();
    }
    for ($i = 1; $i <= $grower_count; $i++) {
        $name = "Grower $i";
        $desc = "Grower Number: $i";
        $stmt->bind_param("ssi", $name, $desc, $client_id);
        $stmt->execute();
    }

    $message = "Inserted $shead_count Sheads, $chick_count Chicks, $grower_count Growers successfully!";
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['number_of_motor'])) {
    $number_of_motor = (int)$_POST['number_of_motor'];

    $conn->query("DELETE FROM motor_config WHERE client_id = $client_id");

    $stmt = $conn->prepare("INSERT INTO motor_config (motor_number, material_name, client_id, number_of_motor) VALUES (?, ?, ?, ?)");

    for ($i = 1; $i <= $number_of_motor; $i++) {
        $material_name = $_POST["material_motor_$i"];
        $stmt->bind_param("isii", $i, $material_name, $client_id, $number_of_motor);
        $stmt->execute();
    }

    $message = "Inserted $number_of_motor motors successfully!";
}

$motors = $conn->query("SELECT * FROM motor_config WHERE client_id = $client_id");
?>

<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shead & Motor Config Dashboard</title>
<style>
* {margin:0; padding:0; box-sizing:border-box; font-family: Arial, sans-serif;}
body {display:flex; min-height:100vh; background-color:#ADD8E6;}
 /* Sidebar */
.sidebar {
  width: 180px;
  background-color: #2c3e50;
  color: #fff;
  display: flex;
  flex-direction: column;
  padding-top: 15px;
  position: fixed;
  left: 0; top: 0; bottom: 0;
  box-shadow: 2px 0 10px rgba(0,0,0,0.2);
}
.sidebar h2 {
  text-align: center;
  margin-bottom: 20px;
  font-size: 16px;
  color: #ecf0f1;
}
.sidebar a {
  padding: 8px 12px;
  text-decoration: none;
  color: #ecf0f1;
  font-size: 13px;
  transition: all 0.3s;
}
.sidebar a:hover {
  background-color: #34495e;
  padding-left: 20px;
}

 /* Main Content */
    .main-content {
      margin-left: 180px; /* match sidebar width */
      flex: 1;
      padding: 40px;
      overflow-y: auto;
    }

    .main-content h2 {
      margin-bottom: 20px;
      color: #2c3e50;
      font-size: 28px;
    }
.forms-container {display:flex; gap:40px; align-items:flex-start;}
form {background-color:#fff; padding:30px; border-radius:8px; box-shadow:0 0 15px rgba(0,0,0,0.1); width:100%;}
form label {display:block; margin-bottom:8px; font-weight:bold;}
form input[type="number"], select {width:100%; padding:10px; margin-bottom:20px; border-radius:5px; border:1px solid #ccc; font-size:16px;}
form button {padding:10px 20px; background-color:#2980b9; color:#fff; border:none; border-radius:5px; font-size:16px; cursor:pointer; transition: background 0.3s;}
form button:hover {background-color:#3498db;}
.message {margin-bottom:20px; color:green; font-weight:bold;}
.current-counts {background-color:#ecf0f1; padding:15px; margin-bottom:20px; border-radius:8px; color:#2c3e50; font-weight:bold;}
.current-counts p {margin-bottom:10px; font-size:16px;}
/* Popup Modal */
.modal {
  display:none;
  position:fixed;
  z-index:999;
  left:0;
  top:0;
  width:100%;
  height:100%;
  background-color:rgba(0,0,0,0.6);
}
.modal-content {
  background-color:#fff;
  margin:10% auto;
  padding:20px;
  border-radius:10px;
  width:80%;
  max-width:700px;
}
.close-btn {
  float:right;
  font-size:20px;
  font-weight:bold;
  cursor:pointer;
  color:red;
}
.motor-table table {width:100%; border-collapse:collapse;}
.motor-table th, .motor-table td {border:1px solid #ccc; padding:10px; text-align:center;}
.motor-table th {background-color:#2980b9; color:#fff;}
</style>

<script>
function generateMotorDropdowns() {
    const count = document.getElementById('number_of_motor').value;
    const container = document.getElementById('motor_dropdowns');
    container.innerHTML = '';

    for (let i = 1; i <= count; i++) {
        const div = document.createElement('div');
        div.innerHTML = `
            <label>Motor ${i} - Select Material:</label>
            <select name="material_motor_${i}" required>
                <option value="">Select Material</option>
                ${window.rawMaterials.map(mat => `<option value="${mat}">${mat}</option>`).join('')}
            </select>
        `;
        container.appendChild(div);
    }
}

// Popup control
function showMotorPopup() {
  document.getElementById("motorModal").style.display = "block";
}
function closeMotorPopup() {
  document.getElementById("motorModal").style.display = "none";
}
</script>
</head>

<body>
 <div class="sidebar">
    <h2>Dashboard</h2>
    <a href="http://localhost:8080/php/index.php">🏠 Home</a>
    <a href="http://localhost:8080/php/shead_config.php">⚙️ Configuration</a>
    <a href="http://localhost:8080/php/feed_formula_json_to_web.php">📊 Feed Formula</a>
    <a href="http://localhost:8080/php/report.php">📊 Report</a>
    <a href="https://sunfra.com/">💬 Support</a>
  </div>

<div class="main-content">
    <?php if($message) echo "<div class='message'>$message</div>"; ?>

    <div class="current-counts">
        <p><strong>Current Sheads:</strong> <?php echo $current_sheads; ?></p>
        <p><strong>Current Chick Sheads:</strong> <?php echo $current_chicks; ?></p>
        <p><strong>Current Growers Sheads:</strong> <?php echo $current_growers; ?></p>
    </div>

    <div class="forms-container">
        <form method="POST">
            <h2>Create Sheads, Chicks & Growers</h2>
            <label for="shead_count">Number of Sheads:</label>
            <input type="number" id="shead_count" name="shead_count" min="0" required>

            <label for="chick_count">Number of Chicks:</label>
            <input type="number" id="chick_count" name="chick_count" min="0" required>

            <label for="grower_count">Number of Growers:</label>
            <input type="number" id="grower_count" name="grower_count" min="0" required>

            <button type="submit">Submit</button>
        </form>

        <form method="POST">
            <h2>Motor Configuration</h2>
            <label for="number_of_motor">How many motors you have?</label>
            <input type="number" id="number_of_motor" name="number_of_motor" min="1" max="20" onchange="generateMotorDropdowns()" required>

            <div id="motor_dropdowns"></div>

            <button type="submit">Save Motors</button>
            <button type="button" style="background-color:#16a085; margin-left:10px;" onclick="showMotorPopup()">Show</button>
        </form>
    </div>
</div>

<div id="motorModal" class="modal">
  <div class="modal-content">
    <span class="close-btn" onclick="closeMotorPopup()">&times;</span>
    <h2>Motor Configuration Details</h2>
    <div class="motor-table">
      <table>
        <tr>
          <th>Motor Number</th>
          <th>Material Name</th>
        </tr>
        <?php
        $motors->data_seek(0);
        while($row = $motors->fetch_assoc()) {
            echo "<tr><td>{$row['motor_number']}</td><td>{$row['material_name']}</td></tr>";
        }
        ?>
      </table>
    </div>
  </div>
</div>

<script>
window.rawMaterials = <?php echo json_encode($raw_materials); ?>;
</script>
</body>
</html>
