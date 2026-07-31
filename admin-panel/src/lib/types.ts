/**
 * Tipos que espelham os schemas do backend.
 *
 * Escritos a mao em vez de gerados do OpenAPI: sao poucos e estaveis, e a
 * geracao exigiria um passo de build a mais no ciclo. Ao mexer num schema do
 * backend, ajuste aqui — o `npm run build` acusa o que ficou incompativel.
 */

export type UserRole = "owner" | "hr" | "viewer";
export type EmployeeStatus = "active" | "inactive" | "suspended";
export type EntryType = "in" | "out" | "break_start" | "break_end";
export type LocationMethod = "beacon" | "wifi" | "gps" | "none";
export type TimeEntryStatus = "approved" | "pending_review" | "rejected";
export type BeaconProtocol = "eddystone" | "ibeacon" | "mac";

export type AdminProfile = {
  id: string;
  name: string;
  email: string;
  role: UserRole;
};

export type TenantInfo = {
  id: string;
  name: string;
  slug: string;
};

export type EmployeeSummary = {
  id: string;
  external_code: string;
  name: string;
  job_title: string | null;
  status: EmployeeStatus;
  hired_at: string | null;
};

export type EmployeeDetail = EmployeeSummary & {
  cpf: string | null;
  email: string | null;
  phone: string | null;
  default_site_id: string | null;
  terminated_at: string | null;
  has_app_credentials: boolean;
  active_face_templates: number;
  created_at: string;
};

export type FaceTemplate = {
  id: string;
  quality_score: number | null;
  model_name: string;
  model_version: string;
  is_active: boolean;
  created_at: string;
};

export type RejectedImage = {
  filename: string;
  reason: string;
  issues: string[];
};

export type EnrollmentResult = {
  employee_id: string;
  created: FaceTemplate[];
  rejected: RejectedImage[];
  deactivated_previous: number;
  consent_id: string;
};

export type Site = {
  id: string;
  name: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  geofence_radius_m: number;
  timezone: string;
  is_active: boolean;
};

export type SiteDetail = Site & {
  beacon_count: number;
  wifi_count: number;
  created_at: string;
};

export type Beacon = {
  id: string;
  site_id: string;
  label: string;
  protocol: BeaconProtocol;
  eddystone_namespace: string | null;
  eddystone_instance: string | null;
  ibeacon_uuid: string | null;
  ibeacon_major: number | null;
  ibeacon_minor: number | null;
  mac_address: string | null;
  min_rssi: number;
  is_active: boolean;
};

export type WifiNetwork = {
  id: string;
  site_id: string;
  ssid: string;
  bssid: string | null;
  label: string | null;
  is_active: boolean;
};

export type TimeEntry = {
  id: string;
  employee_id: string;
  entry_type: EntryType;
  recorded_at: string;
  client_recorded_at: string | null;
  status: TimeEntryStatus;
  decision_reason: string | null;
  face_match_score: number | null;
  liveness_passed: boolean | null;
  location_method: LocationMethod;
  location_confidence: number | null;
  site_id: string | null;
  beacon_id: string | null;
  wifi_network_id: string | null;
  beacon_rssi: number | null;
  distance_to_site_m: number | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

export type TimeEntryWithEmployee = TimeEntry & {
  employee_name: string;
  employee_code: string;
  site_name: string | null;
};

export type Paginated<T> = {
  items: T[];
  total: number;
};
