terraform {
  cloud {
    organization = "leif-lab3"
    workspaces {
      name = "tftest"
    }
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0.0, < 5.0.0"
    }
  }
}

provider "azurerm" {
  features {}
}
