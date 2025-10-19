# Event Aggregator System

> Tugas Ujian Tengah Semester - Sistem Paralel dan Terdistribusi

**Dibuat oleh**: Ardiansyah Bin Sangkala
**NIM**: 11211016  
**Mata kuliah**: Sistem Paralel dan Terdistribusi
**Kelas**: B  

---
## Tentang Tugas

Ini adalah sistem agregasi event terdistribusi yang saya buat untuk memenuhi UTS mata kuliah Sistem Paralel dan Terdistribusi. Sistem ini menangani event dari berbagai sumber dan memastikan tidak ada event yang diproses lebih dari satu kali (deduplication) meskipun dikirim berulang kali.

### Masalah yang Perlu diselesaikan

Dalam sistem terdistribusi, sering terjadi pengiriman event yang berulang karena network retry atau failure. Sistem ini memastikan:
- Event yang sama tidak diproses dua kali
- Data tetap konsisten meskipun ada pengiriman ulang
- Semua event tercatat dengan baik

### Cara Kerja Sistem

Sistem menerima event melalui REST API, mengecek apakah event tersebut sudah pernah diproses sebelumnya menggunakan database SQLite, lalu menyimpan event yang benar-benar baru. Event diproses secara asynchronous.

---
## Fitur Utama Dari Tugas ini

1. **Deduplication** - Deteksi dan buang event duplikat
2. **Idempotency** - Event yang sama selalu menghasilkan efek yang sama
3. **Persistent Storage** - Data tersimpan di SQLite, tidak hilang saat restart
4. **REST API** - Interface yang mudah digunakan
5. **Async Processing** - 5 worker bekerja paralel untuk kecepatan
6. **Docker Support** - Mudah di-deploy

---
## Cara Menjalankan

### Persiapan Tahap Awal

Pastikan sudah terinstall:
- Python 3.11 atau lebih baru
- Docker Desktop (untuk menjalankan container)

### Langkah 1: Jalankan Langsung (Development)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Jalankan server:
```bash
python -m uvicorn src.main:app --reload --port 8080
```

3. Buka browser ke http://localhost:8080/docs untuk melihat dokumentasi API

### Langkah 2: Jalankan dengan Docker (Recommended)

1. Build Docker image:
```bash
docker build -t uts-aggregator .
```

2. Jalankan container:
```bash
docker run -p 8080:8080 uts-aggregator
```

3. Akses API di http://localhost:8080/docs

### Langkah 3: Docker Compose

Untuk menjalankan aggregator beserta publisher simulator sekaligus:

```bash
docker-compose up -d
```

Lihat logsnya:
```bash
docker-compose logs -f
```

Stop semua service:
```bash
docker-compose down
```

---

## Cara Menggunakan API

### 1. Kirim Event

Endpoint: `POST /publish`

Contoh request:
```bash
curl -X POST http://localhost:8080/publish \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "order.created",
    "event_id": "order_12345",
    "timestamp": "2025-10-19T10:00:00Z",
    "source": "order-service",
    "payload": {
      "order_id": 12345,
      "customer": "John Doe",
      "total": 150000
    }
  }'
```

Response jika berhasil:
```json
{
  "status": "success",
  "message": "Processed 1 events",
  "details": {
    "accepted": 1,
    "rejected": 0,
    "duplicates_immediate": 0
  }
}
```

### 2. Kirim Event Duplikat (untuk testing)

Kirim event yang sama lagi:
```bash
curl -X POST http://localhost:8080/publish \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "order.created",
    "event_id": "order_12345",
    "timestamp": "2025-10-19T10:05:00Z",
    "source": "order-service",
    "payload": {
      "order_id": 12345,
      "customer": "John Doe",
      "total": 150000
    }
  }'
```

Response (duplicate terdeteksi):
```json
{
  "status": "success",
  "message": "Processed 1 events",
  "details": {
    "accepted": 0,
    "rejected": 1,
    "duplicates_immediate": 1
  }
}
```

### 3. Lihat Statistik

Endpoint: `GET /stats`

```bash
curl http://localhost:8080/stats
```

Response:
```json
{
  "received": 2,
  "unique_processed": 1,
  "duplicate_dropped": 1,
  "topics": {
    "order.created": 1
  },
  "uptime": 123.45
}
```

### 4. Lihat Semua Event yang Sudah Diproses

Endpoint: `GET /events`

```bash
curl http://localhost:8080/events
```

Atau filter berdasarkan topic:
```bash
curl http://localhost:8080/events?topic=order.created
```

### 5. Health Check

Endpoint: `GET /health`

```bash
curl http://localhost:8080/health
```

---

## Testing

Saya sudah membuat 10 automated tests untuk memastikan sistem bekerja dengan baik:

### Jalankan Semua Test

```bash
python -m pytest tests/ -v
```

Hasil test:
- test_deduplication_basic - Tes deteksi duplikat
- test_persistence_after_restart - Tes persistensi data
- test_schema_validation - Tes validasi input
- test_stats_consistency - Tes konsistensi statistik
- test_get_events_filtering - Tes filter event
- test_stress_5000_events - Tes dengan 5000+ event
- test_concurrent_publishing - Tes concurrent access
- test_idempotency_guarantee - Tes idempotency
- test_batch_vs_single_publish - Tes batch processing
- test_uptime_tracking - Tes monitoring

### Jalankan Test Spesifik

Misalnya untuk stress test:
```bash
python -m pytest tests/test_aggregator.py::test_stress_5000_events -v -s
```

---

## Struktur Project

```
uts-event-aggregator/
├── src/                     
│   ├── models.py             
│   ├── dedup_store.py        
│   ├── aggregator.py         
│   ├── main.py               
│   └── publisher.py         
├── tests/                     
│   └── test_aggregator.py   
├── requirements.txt          
├── Dockerfile               
├── docker-compose.yml        
└── README.md                 
```

---

## Arsitektur Sistem

```
┌──────────────┐
│   Client     │ → Kirim event via HTTP
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│   FastAPI        │ → Validasi & terima request
│   (REST API)     │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Event Aggregator │ → 5 worker proses event
│ (Async Queue)    │   secara parallel
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  Dedup Store     │ → Simpan di SQLite
│  (SQLite DB)     │   Cek duplikat
└──────────────────┘
```

**Flow:**
1. Client kirim event ke `/publish`
2. FastAPI validasi format event
3. Event masuk ke queue internal
4. 5 worker ambil dari queue dan proses
5. Setiap event dicek di database: sudah pernah diproses atau belum?
6. Kalau baru, simpan. Kalau duplikat, buang.

---

## Keputusan Desain

### Kenapa Pakai SQLite?

Saya pilih SQLite karena:
- Mudah digunakan (tidak perlu setup server database)
- Sudah built-in di Python
- Mendukung ACID transactions (data konsisten)
- File database bisa di-backup dengan mudah
- Cukup untuk kebutuhan UTS ini

### Kenapa 5 Worker?

Setelah testing, 5 worker memberikan performa terbaik:
- Lebih cepat dari 1 worker (sequential)
- Tidak terlalu banyak sehingga tidak bentrok di database
- Bisa process sekitar 190 events per detik

### Kenapa At-Least-Once + Idempotency?

Dalam sistem terdistribusi, kita tidak bisa jamin "exactly once delivery" karena network bisa error. Jadi saya implementasi:
- **At-least-once**: Event boleh terkirim berulang kali
- **Idempotency**: Event yang sama tidak akan diproses dua kali

Kombinasi keduanya memberikan efek "exactly once" dari sisi bisnis logic.

---

## Hasil Dari Testing

### Performa

Berdasarkan stress test dengan 5000+ event:
- **Throughput**: ~190 events per detik
- **Akurasi deduplication**: 100%
- **Memory usage**: ~120 MB (peak saat processing)
- **Response time**: < 100ms untuk single event

### Test Coverage

Total 10 test cases, hasil:
- 9-10 test PASSED (90-100%)
- Functional test: Semua passed
- Stress test: 5000 unique events + 1000 duplicates processed successfully

---

## Asumsi dan Limitasi

### Asumsi

1. Event dengan `(topic, event_id)` yang sama dianggap duplikat
2. Perbedaan timestamp pada event duplikat diabaikan
3. System di-deploy sebagai single instance (tidak distributed)
4. Ordering hanya dijamin per-topic, tidak global

### Limitasi

1. Single instance - tidak bisa horizontal scaling
2. SQLite single-writer - bottleneck untuk write-heavy workload
3. In-memory queue - event hilang kalau service crash sebelum diproses
4. Tidak ada authentication/authorization

Untuk production, akan butuh upgrade ke:
- Message queue (RabbitMQ/Kafka)
- Distributed database (PostgreSQL/Redis)
- Load balancer untuk multiple instances

---

## Troubleshooting

### Port 8080 sudah digunakan

Gunakan port lain:
```bash
python -m uvicorn src.main:app --port 9090
```

### Docker build error

Pastikan Docker Desktop running dan internet tersedia untuk download dependencies.

### Note: Apabila saat melakukan test gagal terus, naikkan timeout nya

Edit di bagian file `tests/test_aggregator.py` line 220:
```python
assert elapsed < 35.0  # Naikkan jika laptop lambat
```

### Database locked

Stop semua instance yang running, lalu hapus file `dedup_store.db` dan jalankan ulang.

---

## Referensi

Konsep dan teori yang digunakan dalam project ini:

1. **Distributed Systems** - (Intro hingga Consistency and Replication)[Distributed systems: principles and paradigms I Andrew S. Tanenbaum, Maarten Van Steen.].

Detail lengkap ada di file `report.pdf`.

## Catatan Akhir

Project ini dibuat sebagai bagian dari penilaian UTS Sistem Paralel dan Terdistribusi. Semua kode ditulis sendiri dengan referensi dari dokumentasi resmi Python, FastAPI, dan SQLite. Konsep distributed systems mengacu pada  buku utama (Intro hingga Consistency and Replication)[Distributed systems: principles and paradigms I Andrew S. Tanenbaum, Maarten Van Steen.].
