terraform {
  required_version = "~>1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~>4.0"
    }

    azapi = {
      source  = "Azure/azapi"
      version = "~>2.0"
    }

    time = {
      source  = "hashicorp/time"
      version = "~>0.9"
    }

    tls = {
      source  = "hashicorp/tls"
      version = "~>4.0"
    }

    # azuredevops = {
    #   source = "microsoft/azuredevops"
    #   version = ">= 0.1.0"
    # }
  }

  backend "local" {
    path = "./terraform.tfstate"
  }

  #  backend "remote" {
  #    organization = "leif-lab3"
  #    hostname     = "app.terraform.io"
  #
  #    workspaces {
  #      prefix = "sftp-"
  #    }
  #  }
}
