locals {
  fck_nat_ami_publisher_account_id = "568608671756"
}

data "aws_ami" "fck_nat" {
  owners = [local.fck_nat_ami_publisher_account_id]
  filter {
    name   = "name"
    values = ["fck-nat-al2023-hvm-1.4.0-20261109-arm64-ebs"]
  }
}

resource "aws_subnet" "nat" {
  lifecycle { prevent_destroy = true }
  vpc_id            = aws_vpc.workers.id
  availability_zone = var.azs[0]
  cidr_block        = cidrsubnet(local.vpc_cidr, 8, 255)
  tags              = { Name = "nolift-k3s-nat" }
}

resource "aws_route_table" "nat" {
  lifecycle { prevent_destroy = true }
  vpc_id = aws_vpc.workers.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.workers.id
  }
}

resource "aws_route_table_association" "nat" {
  lifecycle { prevent_destroy = true }
  subnet_id      = aws_subnet.nat.id
  route_table_id = aws_route_table.nat.id
}

resource "aws_security_group" "nat" {
  lifecycle { prevent_destroy = true }
  name   = "nolift-k3s-fck-nat"
  vpc_id = aws_vpc.workers.id
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [for subnet in aws_subnet.workers : subnet.cidr_block]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "fck_nat" {
  lifecycle { prevent_destroy = true }
  ami                         = data.aws_ami.fck_nat.id
  instance_type               = "t4g.nano"
  subnet_id                   = aws_subnet.nat.id
  vpc_security_group_ids      = [aws_security_group.nat.id]
  associate_public_ip_address = true
  source_dest_check           = false
  metadata_options { http_tokens = "required" }
  tags       = { Name = "nolift-k3s-fck-nat" }
  depends_on = [aws_route_table_association.nat]
}
